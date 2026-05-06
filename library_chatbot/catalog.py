from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib import error, parse, request
import re


DEFAULT_CATALOG_BASE_URL = "https://catalog.iitgn.ac.in"
DETAIL_PATH = "/cgi-bin/koha/opac-detail.pl"
SEARCH_PATH = "/cgi-bin/koha/opac-search.pl"


@dataclass(frozen=True)
class CatalogRecord:
    title: str
    source_url: str
    authors: str = ""
    isbn: str = ""
    call_number: str = ""
    status: str = ""
    due_date: str = ""
    barcode: str = ""
    item_type: str = ""
    confidence: float = 0.0

    @property
    def is_available(self) -> bool:
        return "available" in self.status.lower()


@dataclass(frozen=True)
class CatalogSearchResult:
    query: str
    search_url: str
    records: list[CatalogRecord]
    error: str = ""

    @property
    def found(self) -> bool:
        return bool(self.records)


class KohaCatalogClient:
    def __init__(
        self,
        base_url: str = DEFAULT_CATALOG_BASE_URL,
        timeout_seconds: float = 8.0,
        max_detail_pages: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_detail_pages = max(1, max_detail_pages)

    def search(self, query: str) -> CatalogSearchResult:
        clean_query = " ".join(query.split())
        search_url = self.search_url(clean_query)
        if not clean_query:
            return CatalogSearchResult(query=clean_query, search_url=search_url, records=[])

        try:
            html = self._fetch(search_url)
        except RuntimeError as exc:
            return CatalogSearchResult(
                query=clean_query,
                search_url=search_url,
                records=[],
                error=str(exc),
            )

        if _looks_like_no_results(html):
            return CatalogSearchResult(query=clean_query, search_url=search_url, records=[])

        detail_urls = _extract_detail_urls(html, self.base_url)
        if _is_detail_page(search_url) and not detail_urls:
            detail_urls = [search_url]

        records: list[CatalogRecord] = []
        for detail_url in detail_urls[: self.max_detail_pages]:
            try:
                detail_html = self._fetch(detail_url)
            except RuntimeError:
                continue
            record = _parse_detail_page(detail_html, detail_url)
            if record is not None:
                records.append(_score_record(record, clean_query))

        records.sort(key=lambda record: record.confidence, reverse=True)
        return CatalogSearchResult(query=clean_query, search_url=search_url, records=records)

    def search_url(self, query: str) -> str:
        return f"{self.base_url}{SEARCH_PATH}?q={parse.quote_plus(query)}"

    def _fetch(self, url: str) -> str:
        req = request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36 IITGN-Library-Chatbot/1.0"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": f"{self.base_url}/cgi-bin/koha/opac-main.pl",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                html = response.read().decode(charset, errors="replace")
        except error.HTTPError as exc:
            raise RuntimeError(f"catalog request failed with HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"catalog is unreachable: {exc}") from exc
        if _looks_like_bot_challenge(html):
            raise RuntimeError("catalog blocked automated lookup with a bot-check page")
        return html


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "li", "tr", "td", "th", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "li", "tr", "td", "th", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return "\n".join(
            line.strip()
            for line in "".join(self.parts).splitlines()
            if line.strip()
        )


def _extract_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL))
    return parser.text()


def _extract_detail_urls(html: str, base_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r'href=["\']([^"\']*opac-detail\.pl\?biblionumber=\d+[^"\']*)', html, re.IGNORECASE):
        url = parse.urljoin(base_url, match.group(1).replace("&amp;", "&"))
        if url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def _looks_like_no_results(html: str) -> bool:
    text = _extract_text(html).lower()
    return any(
        phrase in text
        for phrase in (
            "no results found",
            "no results match your search",
            "your search returned no results",
        )
    )


def _looks_like_bot_challenge(html: str) -> bool:
    text = _extract_text(html).lower()
    return any(
        phrase in text
        for phrase in (
            "making sure you're not a bot",
            "checking if the site connection is secure",
            "enable javascript and cookies to continue",
        )
    )


def _is_detail_page(url: str) -> bool:
    return "opac-detail.pl" in url


def _parse_detail_page(html: str, source_url: str) -> CatalogRecord | None:
    text = _extract_text(html)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    title = _extract_title(html, lines)
    if not title:
        return None

    holdings = _first_holdings_row(html)
    authors = _line_after_label(lines, "By:")
    isbn = _line_after_label(lines, "ISBN:")
    call_number = holdings.get("call number", "") or _holding_value(lines, "Call number") or _line_after_label(lines, "DDC classification:")
    status = holdings.get("status", "") or _holding_value(lines, "Status")
    due_date = holdings.get("date due", "") or _holding_value(lines, "Date due")
    barcode = holdings.get("barcode", "") or _holding_value(lines, "Barcode")
    item_type = holdings.get("item type", "") or _holding_value(lines, "Item type")

    return CatalogRecord(
        title=title,
        authors=authors,
        isbn=isbn,
        call_number=call_number,
        status=status,
        due_date=due_date,
        barcode=barcode,
        item_type=item_type,
        source_url=source_url,
    )


def _extract_title(html: str, lines: list[str]) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if match:
        text = _strip_tags(match.group(1))
        text = re.sub(r"^\s*Details\s+for\s*:?\s*", "", text, flags=re.IGNORECASE)
        return _clean_title(text)

    for line in lines:
        if line.lower().startswith("details for"):
            return _clean_title(re.sub(r"^Details for:?\s*", "", line, flags=re.IGNORECASE))
    return _clean_title(lines[0])


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).replace("&rsaquo;", " ").strip()


def _first_holdings_row(html: str) -> dict[str, str]:
    for table_match in re.finditer(r"<table\b.*?</table>", html, re.IGNORECASE | re.DOTALL):
        table_html = table_match.group(0)
        if "Call number" not in table_html or "Status" not in table_html:
            continue
        rows = re.findall(r"<tr\b.*?</tr>", table_html, re.IGNORECASE | re.DOTALL)
        if len(rows) < 2:
            continue
        headers = [
            _normalize_holding_header(_strip_tags(cell))
            for cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", rows[0], re.IGNORECASE | re.DOTALL)
        ]
        for row in rows[1:]:
            cells = [
                _clean_holding_cell(_strip_tags(cell))
                for cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row, re.IGNORECASE | re.DOTALL)
            ]
            if len(cells) >= len(headers):
                return {
                    header: value
                    for header, value in zip(headers, cells)
                    if header
                }
    return {}


def _normalize_holding_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"\s+›.*$", "", title).strip()
    return title


def _line_after_label(lines: list[str], label: str) -> str:
    normalized_label = label.lower()
    for index, line in enumerate(lines):
        if line.lower().startswith(normalized_label):
            remainder = line[len(label) :].strip()
            if remainder:
                return remainder
            if index + 1 < len(lines):
                return lines[index + 1]
    return ""


def _holding_value(lines: list[str], label: str) -> str:
    label_lower = label.lower()
    for index, line in enumerate(lines):
        if line.lower() == label_lower and index + 1 < len(lines):
            return _clean_holding_cell(lines[index + 1])
    for line in lines:
        if line.lower().startswith(f"{label_lower} "):
            return _clean_holding_cell(line[len(label) :])
    return ""


def _clean_holding_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("(Browse shelf(Opens below))", "")).strip()


def _score_record(record: CatalogRecord, query: str) -> CatalogRecord:
    query_tokens = _tokens(query)
    haystack_tokens = _tokens(" ".join([record.title, record.authors, record.isbn, record.call_number]))
    if not query_tokens:
        score = 0.0
    else:
        overlap = len(set(query_tokens) & set(haystack_tokens))
        score = overlap / len(set(query_tokens))
    normalized_query = " ".join(query.lower().split())
    normalized_title = " ".join(record.title.lower().split())
    if normalized_query and normalized_query in normalized_title:
        score = max(score, 0.92)
    if record.authors and normalized_query in record.authors.lower():
        score = max(score, 0.82)
    if record.isbn and re.sub(r"\D", "", query) in re.sub(r"\D", "", record.isbn):
        score = max(score, 0.95)
    return CatalogRecord(
        title=record.title,
        authors=record.authors,
        isbn=record.isbn,
        call_number=record.call_number,
        status=record.status,
        due_date=record.due_date,
        barcode=record.barcode,
        item_type=record.item_type,
        source_url=record.source_url,
        confidence=min(1.0, score),
    )


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())
