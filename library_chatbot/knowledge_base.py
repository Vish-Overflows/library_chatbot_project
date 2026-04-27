from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import csv
import math
import re
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


DEFAULT_SOURCE = "https://library.iitgn.ac.in/faqs.php"
CATALOG_SOURCE = "catalog"
EJOURNAL_SOURCE = "ejournal"
FAQ_SOURCE = "faq"
REPOSITORY_SOURCE = "repository_publication"
CATALOG_COLUMN_ALIASES = {
    "title": ("title", "book_title", "name", "publication_title", "dc_title"),
    "authors": ("author", "authors", "creator", "contributors", "dc_contributor_author"),
    "isbn": ("isbn", "isbn10", "isbn13", "dc_identifier_isbn"),
    "issn": ("issn", "eissn", "dc_identifier_issn", "dc_relation_issn"),
    "subject": (
        "subject",
        "subjects",
        "keywords",
        "category",
        "categories",
        "subjectname",
        "subject_keywords",
        "main_subject",
        "dc_subject",
        "dc_subject_other",
        "dc_subject_scopus",
        "dc_subject_wos",
    ),
    "call_number": ("call_number", "callno", "classification", "shelfmark"),
    "location": ("location", "shelf_location", "library_location", "branch"),
    "availability": ("availability", "status", "item_status", "active_or_inactive_y"),
    "description": ("description", "summary", "abstract", "notes", "dc_description_abstract"),
    "source": ("source", "source_url", "url", "catalog_url", "title_url", "dc_identifier_uri"),
    "publisher": ("publisher", "publisher_name", "dc_publisher"),
    "resource_type": ("publication_type", "dc_type", "dc_identifier_subtype"),
    "collection": ("collectionname", "location_coll", "dc_source", "dc_relation_ispartof"),
    "coverage": ("coverage", "coverage_y", "coverage_depth", "coverage_notes"),
    "date": ("date", "date_first_issue_online", "dc_date_issued", "dc_date_available"),
    "doi": ("doi", "dc_identifier_doi"),
}

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
NORMALIZATION_MAP = {
    "journals": "journal",
    "phones": "phone",
    "mobile": "phone",
    "mobiles": "phone",
    "calls": "call",
    "calling": "call",
    "talking": "talk",
    "speaking": "talk",
    "loudly": "loud",
    "noisy": "noise",
    "quietly": "quiet",
    "beverages": "drink",
    "drinks": "drink",
    "ebooks": "ebook",
    "e-books": "ebook",
    "fluids": "fluid",
    "statics": "static",
    "mechanical": "mechanic",
    "mechanics": "mechanic",
    "wifi": "internet",
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "for",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "library",
    "libraries",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "the",
    "their",
    "to",
    "use",
    "what",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens: list[str] = []
    for token in TOKEN_PATTERN.findall(normalized):
        token = NORMALIZATION_MAP.get(token, token)
        if token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0

    overlap = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in overlap)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    source_type: str
    title: str
    body: str
    source: str
    metadata: dict[str, str] = field(default_factory=dict)
    title_tokens: Counter[str] = field(default_factory=Counter)
    body_tokens: Counter[str] = field(default_factory=Counter)

    @classmethod
    def create(
        cls,
        id: str,
        source_type: str,
        title: str,
        body: str,
        source: str,
        metadata: dict[str, str] | None = None,
    ) -> "KnowledgeDocument":
        return cls(
            id=id,
            source_type=source_type,
            title=title,
            body=body,
            source=source,
            metadata=metadata or {},
            title_tokens=Counter(tokenize(title)),
            body_tokens=Counter(tokenize(body)),
        )


@dataclass(frozen=True)
class SearchResult:
    title: str
    content: str
    source: str
    source_type: str
    metadata: dict[str, str]
    score: float

    @property
    def question(self) -> str:
        return self.title

    @property
    def answer(self) -> str:
        return self.content


class KnowledgeBase:
    def __init__(self, documents: list[KnowledgeDocument]) -> None:
        self.documents = documents
        self.entries = documents

    @classmethod
    def from_csv(cls, csv_path: str | Path) -> "KnowledgeBase":
        return cls.from_sources(faq_path=csv_path)

    @classmethod
    def from_sources(
        cls,
        faq_path: str | Path,
        catalog_paths: list[str | Path] | None = None,
    ) -> "KnowledgeBase":
        documents = cls._load_faqs(faq_path)
        for catalog_path in catalog_paths or []:
            documents.extend(cls._load_catalog(catalog_path))

        if not documents:
            raise ValueError("No usable knowledge documents found")

        return cls(documents)

    @staticmethod
    def _load_faqs(csv_path: str | Path) -> list[KnowledgeDocument]:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"FAQ file not found: {path}")

        documents: list[KnowledgeDocument] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                question = (row.get("Questions") or row.get("Question") or "").strip()
                answer = (row.get("Answers") or row.get("Answer") or "").strip()
                source = (row.get("Source") or DEFAULT_SOURCE).strip() or DEFAULT_SOURCE
                if not question or not answer:
                    continue
                documents.append(
                    KnowledgeDocument.create(
                        id=f"faq:{index}",
                        source_type=FAQ_SOURCE,
                        title=question,
                        body=answer,
                        source=source,
                        metadata={"question": question},
                    )
                )

        if not documents:
            raise ValueError(f"No usable FAQs found in {path}")

        return documents

    @staticmethod
    def _load_catalog(csv_path: str | Path) -> list[KnowledgeDocument]:
        path = Path(csv_path)
        if path.suffix.lower() == ".xlsx":
            return KnowledgeBase._load_catalog_xlsx(path)
        return KnowledgeBase._load_catalog_csv(path)

    @staticmethod
    def _load_catalog_csv(csv_path: str | Path) -> list[KnowledgeDocument]:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Catalog file not found: {path}")

        documents: list[KnowledgeDocument] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                normalized = _normalize_row(row)
                document = _catalog_document_from_row(path, index, normalized)
                if document is not None:
                    documents.append(document)

        return documents

    @staticmethod
    def _load_catalog_xlsx(xlsx_path: str | Path) -> list[KnowledgeDocument]:
        path = Path(xlsx_path)
        if not path.exists():
            raise FileNotFoundError(f"Catalog file not found: {path}")

        rows = _read_xlsx_rows(path)
        if not rows:
            return []

        headers = [_normalize_column_name(value) for value in rows[0]]
        documents: list[KnowledgeDocument] = []
        for index, row in enumerate(rows[1:], start=1):
            normalized = {
                header: str(row[position] if position < len(row) else "").strip()
                for position, header in enumerate(headers)
                if header
            }
            document = _catalog_document_from_row(path, index, normalized)
            if document is not None:
                documents.append(document)

        return documents

    def search(self, query: str, limit: int = 4) -> list[SearchResult]:
        query_tokens = Counter(tokenize(query))
        scored_results: list[SearchResult] = []
        normalized_query = normalize_text(query)
        for document in self.documents:
            title_score = cosine_similarity(query_tokens, document.title_tokens)
            body_score = cosine_similarity(query_tokens, document.body_tokens)
            score = (0.65 * title_score) + (0.35 * body_score)
            if document.source_type == FAQ_SOURCE:
                score = (0.8 * title_score) + (0.2 * body_score)

            normalized_title = normalize_text(document.title)
            if normalized_query == normalized_title:
                score = 1.0
            elif normalized_query and normalized_query in normalized_title:
                score = max(score, 0.9)
            elif (
                normalized_title
                and len(document.title_tokens) >= 2
                and normalized_title in normalized_query
            ):
                score = max(score, 0.92)
            elif _exact_metadata_match(normalized_query, document.metadata):
                score = max(score, 0.95)
            score = min(1.0, score + _source_intent_boost(query_tokens, document.source_type))
            if score <= 0:
                continue
            scored_results.append(
                SearchResult(
                    title=document.title,
                    content=document.body,
                    source=document.source,
                    source_type=document.source_type,
                    metadata=document.metadata,
                    score=score,
                )
            )

        scored_results.sort(key=lambda result: result.score, reverse=True)
        return _deduplicate_results(scored_results)[:limit]

    def related_questions(self, query: str, limit: int = 3) -> list[str]:
        normalized_query = normalize_text(query)
        related: list[str] = []
        for result in self.search(query, limit=limit + 1):
            if result.source_type != FAQ_SOURCE:
                continue
            if normalize_text(result.title) == normalized_query:
                continue
            related.append(result.title)
            if len(related) == limit:
                break
        return related


def _normalize_column_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def _first_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key, "")
        if value:
            return value
    return ""


def _catalog_document_from_row(
    path: Path,
    index: int,
    normalized: dict[str, str],
) -> KnowledgeDocument | None:
    title = _first_value(normalized, *CATALOG_COLUMN_ALIASES["title"])
    if not title:
        return None

    authors = _first_value(normalized, *CATALOG_COLUMN_ALIASES["authors"])
    isbn = _first_value(normalized, *CATALOG_COLUMN_ALIASES["isbn"])
    issn = _first_value(normalized, *CATALOG_COLUMN_ALIASES["issn"])
    subject = _first_value(normalized, *CATALOG_COLUMN_ALIASES["subject"])
    call_number = _first_value(normalized, *CATALOG_COLUMN_ALIASES["call_number"])
    location = _first_value(normalized, *CATALOG_COLUMN_ALIASES["location"])
    availability = _first_value(normalized, *CATALOG_COLUMN_ALIASES["availability"])
    description = _first_value(normalized, *CATALOG_COLUMN_ALIASES["description"])
    source = _first_value(normalized, *CATALOG_COLUMN_ALIASES["source"]) or "library catalog"
    publisher = _first_value(normalized, *CATALOG_COLUMN_ALIASES["publisher"])
    resource_type = _first_value(normalized, *CATALOG_COLUMN_ALIASES["resource_type"])
    collection = _first_value(normalized, *CATALOG_COLUMN_ALIASES["collection"])
    coverage = _first_value(normalized, *CATALOG_COLUMN_ALIASES["coverage"])
    date = _first_value(normalized, *CATALOG_COLUMN_ALIASES["date"])
    doi = _first_value(normalized, *CATALOG_COLUMN_ALIASES["doi"])
    source_type = _detect_source_type(normalized)

    body_parts = [
        f"Title: {title}",
        f"Type: {resource_type}" if resource_type else "",
        f"Author(s): {authors}" if authors else "",
        f"ISBN: {isbn}" if isbn else "",
        f"ISSN/eISSN: {issn}" if issn else "",
        f"DOI: {doi}" if doi else "",
        f"Subject(s): {subject}" if subject else "",
        f"Publisher: {publisher}" if publisher else "",
        f"Collection/source: {collection}" if collection else "",
        f"Call number: {call_number}" if call_number else "",
        f"Location: {location}" if location else "",
        f"Availability: {availability}" if availability else "",
        f"Coverage: {coverage}" if coverage else "",
        f"Date: {date}" if date else "",
        f"Description: {description}" if description else "",
    ]
    if source_type == EJOURNAL_SOURCE:
        body_parts.insert(1, "Record kind: E-journal/e-resource access record")
    elif source_type == REPOSITORY_SOURCE:
        body_parts.insert(1, "Record kind: IITGN repository publication record")
    body = "\n".join(part for part in body_parts if part)
    metadata = {
        key: value
        for key, value in {
            "title": title,
            "record_kind": source_type,
            "resource_type": resource_type,
            "authors": authors,
            "isbn": isbn,
            "issn": issn,
            "doi": doi,
            "subject": subject,
            "publisher": publisher,
            "collection": collection,
            "call_number": call_number,
            "location": location,
            "availability": availability,
            "coverage": coverage,
            "date": date,
        }.items()
        if value
    }
    return KnowledgeDocument.create(
        id=f"catalog:{path.name}:{index}",
        source_type=source_type,
        title=title,
        body=body,
        source=source,
        metadata=metadata,
    )


def _detect_source_type(normalized: dict[str, str]) -> str:
    if "publication_title" in normalized and (
        "title_url" in normalized
        or "provider_name" in normalized
        or "collectionname" in normalized
        or "coverage_y" in normalized
    ):
        return EJOURNAL_SOURCE
    if "dc_title" in normalized and (
        "handle" in normalized
        or "search_resourceid" in normalized
        or "dc_identifier_uri" in normalized
        or "dc_type" in normalized
    ):
        return REPOSITORY_SOURCE
    return CATALOG_SOURCE


def _normalize_row(row: dict[str | None, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized_key = _normalize_column_name(key)
        if isinstance(value, list):
            normalized[normalized_key] = " ".join(str(item or "").strip() for item in value).strip()
        else:
            normalized[normalized_key] = str(value or "").strip()
    return normalized


def _read_xlsx_rows(path: Path) -> list[list[str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive, ns)
        sheet_name = _first_sheet_name(archive)
        sheet = ET.fromstring(archive.read(sheet_name))
        rows: list[list[str]] = []
        for row in sheet.findall(".//a:sheetData/a:row", ns):
            values: dict[int, str] = {}
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "")
                cell_value = _cell_value(cell, shared_strings, ns)
                values[_column_index(ref)] = cell_value
            if values:
                rows.append([values.get(position, "") for position in range(max(values) + 1)])
        return rows


def _read_shared_strings(archive: ZipFile, ns: dict[str, str]) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(text.text or "" for text in item.findall(".//a:t", ns))
        for item in root.findall("a:si", ns)
    ]


def _first_sheet_name(archive: ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_namespace = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    office_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    relationships = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{rel_namespace}Relationship")
    }
    sheet = workbook.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
    if sheet is None:
        raise ValueError("No worksheets found in Excel file")
    rel_id = sheet.attrib[f"{office_namespace}id"]
    target = relationships[rel_id]
    return f"xl/{target.lstrip('/')}"


def _cell_value(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> str:
    value = cell.find("a:v", ns)
    if value is None or value.text is None:
        inline = cell.find("a:is", ns)
        if inline is None:
            return ""
        return "".join(text.text or "" for text in inline.findall(".//a:t", ns))
    if cell.attrib.get("t") == "s":
        return shared_strings[int(value.text)]
    return value.text


def _column_index(cell_ref: str) -> int:
    letters = "".join(character for character in cell_ref if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + ord(character.upper()) - 64
    return index - 1


def _exact_metadata_match(normalized_query: str, metadata: dict[str, str]) -> bool:
    if not normalized_query:
        return False
    high_precision_fields = {"isbn", "issn", "doi", "call_number"}
    for key in high_precision_fields:
        value = metadata.get(key, "")
        normalized_value = normalize_text(value)
        compact_query = re.sub(r"[^a-z0-9]+", "", normalized_query)
        compact_value = re.sub(r"[^a-z0-9]+", "", normalized_value)
        if compact_query and compact_query == compact_value:
            return True
        if normalized_query and normalized_query == normalized_value:
            return True
    return False


def _source_intent_boost(query_tokens: Counter[str], source_type: str) -> float:
    if source_type == EJOURNAL_SOURCE:
        intent_tokens = {
            "access",
            "active",
            "coverage",
            "ejournal",
            "eresource",
            "issn",
            "journal",
            "journals",
            "provider",
            "subscription",
        }
        return 0.08 if set(query_tokens) & intent_tokens else 0.0
    if source_type == REPOSITORY_SOURCE:
        intent_tokens = {
            "article",
            "author",
            "conference",
            "department",
            "doi",
            "paper",
            "papers",
            "publication",
            "publications",
            "repository",
            "thesis",
            "theses",
        }
        return 0.08 if set(query_tokens) & intent_tokens else 0.0
    if source_type == FAQ_SOURCE:
        intent_tokens = {
            "borrow",
            "card",
            "fine",
            "food",
            "hours",
            "library",
            "membership",
            "policy",
            "rules",
            "timing",
            "wifi",
        }
        return 0.04 if set(query_tokens) & intent_tokens else 0.0
    return 0.0


def _deduplicate_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[tuple[str, str, str, str]] = set()
    unique_results: list[SearchResult] = []
    for result in results:
        key = (
            normalize_text(result.title),
            result.source_type,
            normalize_text(result.source),
            normalize_text(result.metadata.get("collection", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_results.append(result)
    return unique_results
