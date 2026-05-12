from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import uuid4

from library_chatbot.catalog import CatalogRecord, KohaCatalogClient
from library_chatbot.knowledge_base import KnowledgeBase, SearchResult
from library_chatbot.llm import OpenAICompatibleClient
from library_chatbot.storage import ChatStorage, ChatTurn, StoredMessage


GREETING_RESPONSES = {
    "hi": "Hello! How can I help you with IITGN Library today?",
    "hello": "Hello! How can I help you with IITGN Library today?",
    "hey": "Hello! How can I help you with IITGN Library today?",
}

FALLBACK_ANSWER = (
    "I could not verify a direct answer from the current library knowledge base."
)
LOW_CONFIDENCE_NOTICE = (
    "I found a possible library source, but the match is not strong enough for a generated answer. "
    "Please verify it from the source below or contact librarian@iitgn.ac.in."
)
LIBRARY_REDIRECTS = {
    "general": "https://library.iitgn.ac.in/",
    "catalog": "https://catalog.iitgn.ac.in/",
    "faq": "https://library.iitgn.ac.in/faqs.php",
    "repository_publication": "https://repository.iitgn.ac.in/",
    "digital_resources": "https://library.iitgn.ac.in/e_resource_publisherwise.php",
    "off_campus": "https://library.iitgn.ac.in/off-campus-access.php",
    "ill": "https://library.iitgn.ac.in/ill.php",
    "contact": "https://library.iitgn.ac.in/contact.php",
}
GENERATION_CONFIDENCE_MINIMUM = 0.30
SOURCE_REDIRECT_MINIMUM = 0.28
CITATION_CONFIDENCE_MINIMUM = 0.28
SERVICE_SOURCE_TYPES = frozenset({"library_website", "faq"})
EJOURNAL_SOURCE_TYPES = frozenset({"library_website", "faq", "ejournal"})
REPOSITORY_SOURCE_TYPES = frozenset({"repository_publication"})
CATALOG_SOURCE_TYPES = frozenset({"catalog"})
FOLLOW_UP_HINTS = {
    "also",
    "and",
    "that",
    "this",
    "those",
    "these",
    "it",
    "they",
    "them",
    "there",
    "then",
    "weekend",
    "weekends",
    "weekday",
    "weekdays",
    "timing",
    "timings",
    "hours",
    "rules",
    "rule",
    "policy",
    "policies",
    "charges",
    "fine",
    "fees",
}
REFERENTIAL_PATTERN = re.compile(r"\b(it|they|them|that|this|there|those|these|also)\b", re.IGNORECASE)
PHONE_CALL_PATTERN = re.compile(r"\b(phone\s+call|call\s+someone|take\s+calls?|make\s+calls?|talk\s+on\s+phone)\b", re.IGNORECASE)
BORROWING_PATTERN = re.compile(r"\b(borrow|borrowing|loan|loans|issue|issuing|renew|renewal|rfid)\b", re.IGNORECASE)
HOURS_INTENT_PATTERN = re.compile(
    r"\b("
    r"hours?|timings?|opening|closing|open|close|semester|vacation|24x7|24/7"
    r")\b",
    re.IGNORECASE,
)
CONTACT_INTENT_PATTERN = re.compile(
    r"\b(contact|email|phone|number|staff|librarian|circulation|acquisition|services team)\b",
    re.IGNORECASE,
)
OFF_CAMPUS_INTENT_PATTERN = re.compile(
    r"\b(off[- ]campus|remote|remotexs|vpn|outside campus|from home)\b",
    re.IGNORECASE,
)
ILL_DDS_INTENT_PATTERN = re.compile(
    r"\b(article copy|document delivery|dds|ill|inter library|interlibrary|not available|unavailable article)\b",
    re.IGNORECASE,
)
EJOURNAL_INTENT_PATTERN = re.compile(
    r"\b(e[- ]?journal|journal|e[- ]?resource|database|subscription|coverage|publisher|provider|onos|access to|do you have access)\b",
    re.IGNORECASE,
)
REPOSITORY_INTENT_PATTERN = re.compile(
    r"\b(repository|publication|publications|thesis|theses|doi|research paper|conference paper|patent|author)\b",
    re.IGNORECASE,
)
RULES_INTENT_PATTERN = re.compile(
    r"\b(rule|rules|policy|policies|food|eat|drink|silence|phone|smoking|fine|fee|overdue)\b",
    re.IGNORECASE,
)
SERVICE_INTENT_PATTERN = re.compile(
    r"\b("
    r"service|services|help|contact|email|article copy|document delivery|dds|ill|inter library|"
    r"off[- ]campus|remote|remotexs|vpn|purchase|recommend|acquisition|turnitin|grammarly|"
    r"similarity|research support"
    r")\b",
    re.IGNORECASE,
)
CATALOG_INTENT_PATTERN = re.compile(
    r"\b("
    r"catalog|catalogue|book|books|title|author|authors|isbn|call\s+number|"
    r"do\s+you\s+have|is\s+.+\s+in\s+the\s+library|available|find\s+.+\s+book|"
    r"find\s+.+\s+library|sipser|cormen"
    r")\b",
    re.IGNORECASE,
)
POLICY_INTENT_PATTERN = re.compile(
    r"\b(policy|borrow|borrowing|loan|loans|renew|renewal|rfid|issue|return|fine|fee|hours|timing|rule|rules)\b",
    re.IGNORECASE,
)
CATALOG_QUERY_STOPWORDS = {
    "a",
    "an",
    "available",
    "book",
    "books",
    "catalog",
    "catalogue",
    "can",
    "could",
    "do",
    "find",
    "have",
    "i",
    "in",
    "is",
    "library",
    "me",
    "please",
    "the",
    "there",
    "would",
    "you",
}


@dataclass(frozen=True)
class SourceCitation:
    title: str
    source_type: str
    source_url: str
    confidence: float
    metadata: dict[str, str]


@dataclass(frozen=True)
class ChatResult:
    session_id: str
    answer: str
    source_url: str
    sources: list[SourceCitation]
    related_questions: list[str]
    response_mode: str
    confidence: float


@dataclass(frozen=True)
class QueryRoute:
    intent: str
    allowed_source_types: frozenset[str]
    redirect_key: str
    generation_minimum: float = GENERATION_CONFIDENCE_MINIMUM
    source_minimum: float = SOURCE_REDIRECT_MINIMUM
    similarity_minimum: float | None = None
    policy: str = ""


class ChatService:
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        storage: ChatStorage,
        similarity_threshold: float,
        top_k: int,
        conversation_history_limit: int,
        llm_client: OpenAICompatibleClient | None = None,
        catalog_client: KohaCatalogClient | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.storage = storage
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.conversation_history_limit = conversation_history_limit
        self.llm_client = llm_client
        self.catalog_client = catalog_client

    def answer(self, message: str, session_id: str | None = None) -> ChatResult:
        clean_message = " ".join(message.split())
        if not clean_message:
            raise ValueError("Message cannot be empty")

        session = session_id or str(uuid4())
        recent_turns = self.storage.recent_messages(session, limit=self.conversation_history_limit)
        greeting = GREETING_RESPONSES.get(clean_message.lower())
        if greeting is not None:
            result = ChatResult(
                session_id=session,
                answer=greeting,
                source_url="https://library.iitgn.ac.in/",
                sources=[],
                related_questions=[],
                response_mode="rule",
                confidence=1.0,
            )
            self._store(session, clean_message, result)
            return result

        contextual_query = self._rewrite_with_context(clean_message, recent_turns)
        used_conversation_context = contextual_query != clean_message
        route = self._route_query(clean_message, contextual_query)
        effective_query = self._expand_query(contextual_query, route)

        if route.intent == "CATALOG_AVAILABILITY" and self._should_search_live_catalog(clean_message):
            catalog_result = self._answer_from_live_catalog(clean_message, session)
            if catalog_result is not None:
                return catalog_result

        search_limit = max(self.top_k * 4, 12)
        search_results = self.knowledge_base.search(effective_query, limit=search_limit)
        search_results = self._filter_results_for_route(route, search_results)
        similarity_minimum = route.similarity_minimum or self.similarity_threshold
        if not search_results or search_results[0].score < similarity_minimum:
            if effective_query != clean_message:
                direct_results = self.knowledge_base.search(clean_message, limit=self.top_k)
                direct_results = self._filter_results_for_route(route, direct_results)
                if direct_results and direct_results[0].score > (search_results[0].score if search_results else 0.0):
                    search_results = direct_results
                    effective_query = clean_message

            result = ChatResult(
                session_id=session,
                answer=self._fallback_answer(clean_message, search_results, route),
                source_url=self._redirect_url(clean_message, search_results, route),
                sources=self._source_citations(self._reliable_sources(search_results, route.source_minimum)),
                related_questions=self.knowledge_base.related_questions(effective_query, limit=3),
                response_mode="fallback",
                confidence=search_results[0].score if search_results else 0.0,
            )
            self._store(session, clean_message, result)
            return result

        top_result = search_results[0]
        if top_result.score < route.source_minimum:
            result = ChatResult(
                session_id=session,
                answer=self._fallback_answer(clean_message, search_results, route),
                source_url=self._redirect_url(clean_message, search_results, route),
                sources=self._source_citations(self._reliable_sources(search_results, route.source_minimum)),
                related_questions=self.knowledge_base.related_questions(effective_query, limit=3),
                response_mode="fallback",
                confidence=top_result.score,
            )
            self._store(session, clean_message, result)
            return result

        allow_generation = top_result.score >= route.generation_minimum
        answer_text, response_mode = self._compose_answer(
            clean_message,
            effective_query,
            search_results,
            recent_turns,
            allow_generation=allow_generation,
            route=route,
        )
        if used_conversation_context and response_mode == "retrieval":
            response_mode = "contextual_retrieval"
        result = ChatResult(
            session_id=session,
            answer=answer_text,
            source_url=top_result.source,
            sources=self._answer_citations(search_results),
            related_questions=self.knowledge_base.related_questions(effective_query, limit=3),
            response_mode=response_mode,
            confidence=top_result.score,
        )
        self._store(session, clean_message, result)
        return result

    def _compose_answer(
        self,
        message: str,
        effective_query: str,
        search_results: list[SearchResult],
        recent_turns: list[ChatTurn],
        allow_generation: bool,
        route: QueryRoute,
    ) -> tuple[str, str]:
        top_result = search_results[0]
        if self.llm_client is None or not allow_generation:
            return self._compose_retrieval_answer(search_results), "retrieval"

        context_blocks = [
            self._format_context_block(result)
            for result in search_results
        ]
        conversation_history = [
            (turn.user_message, turn.assistant_message)
            for turn in recent_turns
        ]
        try:
            llm_answer = self.llm_client.answer(
                question=message,
                context_blocks=context_blocks,
                conversation_history=conversation_history,
                answer_policy=self._route_answer_policy(route),
            )
            return llm_answer.text, "llm"
        except RuntimeError:
            return top_result.answer, "retrieval"

    def _fallback_answer(self, message: str, search_results: list[SearchResult], route: QueryRoute) -> str:
        redirect_url = self._redirect_url(message, search_results, route)
        contact = self._contact_for_message(message)
        nearby = ""
        reliable_sources = self._reliable_sources(search_results, route.source_minimum)
        if reliable_sources:
            nearby_titles = ", ".join(result.title for result in reliable_sources[:3])
            nearby = f"\n\nClosest related library sources I found: {nearby_titles}."
        return (
            f"{FALLBACK_ANSWER} "
            "The safest next step is to check the relevant library source or contact the right library team."
            f"{nearby}\n\n"
            f"Relevant source: {redirect_url}\n"
            f"Contact: {contact}"
        )

    def _uncertain_answer(self, top_result: SearchResult) -> str:
        source_url = top_result.source or LIBRARY_REDIRECTS["general"]
        return (
            f"{LOW_CONFIDENCE_NOTICE}\n\n"
            f"Possible match: {top_result.title}\n"
            f"Source: {source_url}"
        )

    def _redirect_url(
        self,
        message: str,
        search_results: list[SearchResult],
        route: QueryRoute | None = None,
    ) -> str:
        source_minimum = route.source_minimum if route else SOURCE_REDIRECT_MINIMUM
        if search_results and search_results[0].score >= source_minimum and search_results[0].source:
            return search_results[0].source
        if route:
            return LIBRARY_REDIRECTS[route.redirect_key]

        lowered = message.lower()
        if any(token in lowered for token in ("catalog", "book", "isbn", "borrow", "available", "availability")):
            if any(token in lowered for token in ("borrow", "loan", "renew", "rfid", "issue")):
                return LIBRARY_REDIRECTS["faq"]
            return LIBRARY_REDIRECTS["catalog"]
        if any(token in lowered for token in ("remote", "off-campus", "off campus", "vpn", "remotexs")):
            return LIBRARY_REDIRECTS["off_campus"]
        if any(token in lowered for token in ("journal", "e-resource", "eresource", "database", "article", "paper access")):
            return LIBRARY_REDIRECTS["digital_resources"]
        if any(token in lowered for token in ("ill", "inter library", "interlibrary", "document delivery", "dds")):
            return LIBRARY_REDIRECTS["ill"]
        if any(token in lowered for token in ("contact", "email", "staff", "help")):
            return LIBRARY_REDIRECTS["contact"]
        if any(token in lowered for token in ("paper", "publication", "repository", "thesis", "doi", "author")):
            return LIBRARY_REDIRECTS["repository_publication"]
        if any(token in lowered for token in ("rule", "policy", "hours", "timing", "fine", "fee")):
            return LIBRARY_REDIRECTS["faq"]
        return LIBRARY_REDIRECTS["general"]

    def _contact_for_message(self, message: str) -> str:
        lowered = message.lower()
        if any(token in lowered for token in ("borrow", "loan", "return", "renew", "fine", "overdue", "circulation", "card", "rfid")):
            return "librarycirculation@iitgn.ac.in"
        if any(token in lowered for token in ("purchase", "recommend", "procurement", "acquisition", "subscribe", "book request")):
            return "libraryacquisitions@iitgn.ac.in"
        if any(token in lowered for token in ("remote", "off-campus", "off campus", "remotexs", "vpn", "article", "dds", "ill", "research", "turnitin", "grammarly")):
            return "libraryservices@iitgn.ac.in"
        return "librarian@iitgn.ac.in"

    def _compose_retrieval_answer(self, search_results: list[SearchResult]) -> str:
        top_result = search_results[0]
        if top_result.source_type == "library_website":
            lines = [self._website_answer(top_result)]
            related = [
                result
                for result in search_results[1:4]
                if result.score >= CITATION_CONFIDENCE_MINIMUM
                and result.source_type in {"library_website", "faq"}
                and result.title != top_result.title
            ]
            if related:
                lines.append("")
                lines.append("Related library sources:")
                for result in related:
                    lines.append(f"- {result.title}: {result.source}")
            return "\n".join(lines)

        if top_result.source_type in {"ejournal", "repository_publication", "catalog"}:
            return top_result.answer

        lines = [top_result.answer.strip()]
        related = [
            result
            for result in search_results[1:4]
            if result.score >= CITATION_CONFIDENCE_MINIMUM and result.title != top_result.title
        ]
        if related:
            lines.append("")
            lines.append("Related library options:")
            for result in related:
                lines.append(f"- {result.title}: {result.source}")
        if top_result.source:
            lines.append("")
            lines.append(f"Source: {top_result.source}")
        return "\n".join(line for line in lines if line is not None)

    def _website_answer(self, result: SearchResult) -> str:
        match = re.search(r"Description:\s*(.*)", result.content, re.IGNORECASE | re.DOTALL)
        if match:
            answer = match.group(1).strip()
            answer = re.split(
                r"\n(?:Source|Availability|Subject|Collection|Type):",
                answer,
                maxsplit=1,
            )[0].strip()
        else:
            answer = re.sub(r"^Title:\s*.*?\n", "", result.content, flags=re.IGNORECASE).strip()
        if result.source:
            answer = f"{answer}\n\nSource: {result.source}"
        return answer

    def _should_search_live_catalog(self, message: str) -> bool:
        if self.catalog_client is None:
            return False
        if SERVICE_INTENT_PATTERN.search(message):
            return False
        if POLICY_INTENT_PATTERN.search(message) and not re.search(
            r"\b(do you have|is .+ in the library|find|isbn|author|title|catalog|catalogue)\b",
            message,
            re.IGNORECASE,
        ):
            return False
        return CATALOG_INTENT_PATTERN.search(message) is not None

    def _answer_from_live_catalog(self, message: str, session_id: str) -> ChatResult | None:
        if self.catalog_client is None:
            return None

        catalog_query = self._catalog_query_from_message(message)
        if not catalog_query:
            return None

        result = self.catalog_client.search(catalog_query)
        if result.error:
            chat_result = ChatResult(
                session_id=session_id,
                answer=(
                    "I could not reach the live catalogue just now. "
                    f"You can search it directly here: {result.search_url}"
                ),
                source_url=result.search_url,
                sources=[],
                related_questions=[],
                response_mode="catalog_redirect",
                confidence=0.0,
            )
            self._store(session_id, message, chat_result)
            return chat_result

        confident_records = [
            record
            for record in result.records
            if record.confidence >= 0.45
        ]
        if not confident_records:
            if result.found:
                answer = (
                    "I found possible catalogue matches, but not a confident enough match to answer directly. "
                    f"Please check the catalogue results here: {result.search_url}"
                )
                confidence = result.records[0].confidence
                sources = self._catalog_citations(result.records[:3])
            else:
                answer = (
                    f"I could not find a confident catalogue match for \"{catalog_query}\". "
                    f"Please search the catalogue directly here: {result.search_url}"
                )
                confidence = 0.0
                sources = []
            chat_result = ChatResult(
                session_id=session_id,
                answer=answer,
                source_url=result.search_url,
                sources=sources,
                related_questions=[],
                response_mode="catalog_redirect",
                confidence=confidence,
            )
            self._store(session_id, message, chat_result)
            return chat_result

        answer = self._catalog_answer(catalog_query, confident_records)
        chat_result = ChatResult(
            session_id=session_id,
            answer=answer,
            source_url=confident_records[0].source_url,
            sources=self._catalog_citations(confident_records),
            related_questions=[],
            response_mode="live_catalog",
            confidence=confident_records[0].confidence,
        )
        self._store(session_id, message, chat_result)
        return chat_result

    def _catalog_query_from_message(self, message: str) -> str:
        normalized = " ".join(message.strip().split())
        quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', normalized)
        if quoted:
            return next((left or right for left, right in quoted if left or right), "").strip()

        cleaned = re.sub(r"\b(do you have|can you find|find|is|are|there|any|available|in the library|library|catalogue|catalog)\b", " ", normalized, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(book|books|copy|copies|title|by|about|called|named)\b", " ", cleaned, flags=re.IGNORECASE)
        tokens = [
            token
            for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9.'-]*", cleaned)
            if token.lower() not in CATALOG_QUERY_STOPWORDS
        ]
        return " ".join(tokens).strip() or normalized

    def _catalog_answer(self, query: str, records: list[CatalogRecord]) -> str:
        top = records[0]
        availability = top.status or "status not shown"
        answer_lines = [
            f"Yes, I found a catalogue match for \"{query}\": {top.title}.",
        ]
        if top.authors:
            answer_lines.append(f"Author(s): {top.authors}.")
        if top.call_number:
            answer_lines.append(f"Call number: {top.call_number}.")
        if top.item_type:
            answer_lines.append(f"Item type: {top.item_type}.")
        answer_lines.append(f"Status: {availability}.")
        if top.due_date:
            answer_lines.append(f"Due date: {top.due_date}.")
        answer_lines.append(f"Catalogue record: {top.source_url}")
        if len(records) > 1:
            answer_lines.append("I also found related catalogue records in the sources below.")
        return "\n".join(answer_lines)

    def _catalog_citations(self, records: list[CatalogRecord]) -> list[SourceCitation]:
        citations: list[SourceCitation] = []
        for record in records[:5]:
            citations.append(
                SourceCitation(
                    title=record.title,
                    source_type="live_catalog",
                    source_url=record.source_url,
                    confidence=record.confidence,
                    metadata={
                        key: value
                        for key, value in {
                            "authors": record.authors,
                            "isbn": record.isbn,
                            "call_number": record.call_number,
                            "availability": record.status,
                            "date": record.due_date,
                            "resource_type": record.item_type,
                        }.items()
                        if value
                    },
                )
            )
        return citations

    def _reliable_sources(
        self,
        search_results: list[SearchResult],
        minimum: float = SOURCE_REDIRECT_MINIMUM,
    ) -> list[SearchResult]:
        return [
            result
            for result in search_results
            if result.score >= minimum
        ]

    def _source_citations(self, search_results: list[SearchResult]) -> list[SourceCitation]:
        citations: list[SourceCitation] = []
        for result in search_results[:5]:
            if result.score < CITATION_CONFIDENCE_MINIMUM:
                continue
            citations.append(
                SourceCitation(
                    title=result.title,
                    source_type=result.source_type,
                    source_url=result.source,
                    confidence=result.score,
                    metadata={
                        key: value
                        for key, value in result.metadata.items()
                        if key
                        in {
                            "availability",
                            "authors",
                            "collection",
                            "coverage",
                            "date",
                            "doi",
                            "issn",
                            "publisher",
                            "record_kind",
                            "resource_type",
                            "subject",
                        }
                    },
                )
            )
        return citations

    def _answer_citations(self, search_results: list[SearchResult]) -> list[SourceCitation]:
        if not search_results:
            return []
        top_source_type = search_results[0].source_type
        if top_source_type == "library_website":
            filtered = [
                result
                for result in search_results
                if result.source_type in {"library_website", "faq"}
            ]
            return self._source_citations(filtered)
        if top_source_type == "faq":
            filtered = [
                result
                for result in search_results
                if result.source_type in {"faq", "library_website"}
            ]
            return self._source_citations(filtered)
        return self._source_citations(search_results)

    def _filter_results_for_route(
        self,
        route: QueryRoute,
        search_results: list[SearchResult],
    ) -> list[SearchResult]:
        if not search_results:
            return search_results

        if not route.allowed_source_types:
            return search_results

        return [
            result
            for result in search_results
            if result.source_type in route.allowed_source_types
        ]

    def _route_query(self, message: str, contextual_query: str) -> QueryRoute:
        combined = f"{message} {contextual_query}"
        lowered = combined.lower()

        if ILL_DDS_INTENT_PATTERN.search(combined):
            return QueryRoute(
                intent="SERVICE_ILL_DDS",
                allowed_source_types=SERVICE_SOURCE_TYPES,
                redirect_key="ill",
                policy="Answer as a library service question about ILL/DDS/article help. Do not use e-journal or repository records as proof of service policy.",
            )
        if OFF_CAMPUS_INTENT_PATTERN.search(combined):
            return QueryRoute(
                intent="SERVICE_OFF_CAMPUS",
                allowed_source_types=SERVICE_SOURCE_TYPES,
                redirect_key="off_campus",
                policy="Answer using off-campus access and RemoteXS/VPN evidence only.",
            )
        if HOURS_INTENT_PATTERN.search(combined):
            return QueryRoute(
                intent="SERVICE_HOURS",
                allowed_source_types=SERVICE_SOURCE_TYPES,
                redirect_key="faq",
                policy="Answer library hours/timings only from FAQ or library website evidence.",
            )
        if CONTACT_INTENT_PATTERN.search(combined):
            return QueryRoute(
                intent="SERVICE_CONTACT",
                allowed_source_types=SERVICE_SOURCE_TYPES,
                redirect_key="contact",
                policy="Route the user to the most specific contact email or phone number in the evidence.",
            )
        if BORROWING_PATTERN.search(combined):
            return QueryRoute(
                intent="SERVICE_BORROWING",
                allowed_source_types=SERVICE_SOURCE_TYPES,
                redirect_key="faq",
                policy="Answer borrowing/circulation questions only from FAQ or library website evidence.",
            )
        if RULES_INTENT_PATTERN.search(combined):
            return QueryRoute(
                intent="SERVICE_RULES",
                allowed_source_types=SERVICE_SOURCE_TYPES,
                redirect_key="faq",
                generation_minimum=0.28,
                policy="Answer rules/policy questions only from FAQ or library website evidence.",
            )
        if self._looks_like_repository_query(combined):
            return QueryRoute(
                intent="REPOSITORY_PUBLICATION",
                allowed_source_types=REPOSITORY_SOURCE_TYPES,
                redirect_key="repository_publication",
                source_minimum=0.25,
                policy="Answer as a repository/publication lookup. Include available publication metadata and repository URL.",
            )
        if self._looks_like_ejournal_query(combined):
            return QueryRoute(
                intent="EJOURNAL_ACCESS",
                allowed_source_types=EJOURNAL_SOURCE_TYPES,
                redirect_key="digital_resources",
                policy="Answer as an e-journal/e-resource access question. Use e-journal metadata plus website/FAQ access guidance.",
            )
        if self._looks_like_catalog_query(message):
            return QueryRoute(
                intent="CATALOG_AVAILABILITY",
                allowed_source_types=CATALOG_SOURCE_TYPES,
                redirect_key="catalog",
                policy="Answer as a catalog availability lookup. If live catalog evidence is unavailable, route to the catalog search.",
            )
        if "library" in lowered or SERVICE_INTENT_PATTERN.search(combined) or POLICY_INTENT_PATTERN.search(combined):
            return QueryRoute(
                intent="GENERAL_LIBRARY",
                allowed_source_types=SERVICE_SOURCE_TYPES,
                redirect_key="general",
                generation_minimum=0.34,
                policy="Answer as a general front-desk library question using only website and FAQ evidence.",
            )
        return QueryRoute(
            intent="UNKNOWN",
            allowed_source_types=SERVICE_SOURCE_TYPES,
            redirect_key="general",
            generation_minimum=0.45,
            source_minimum=0.34,
            policy="If the evidence does not clearly answer the user, give a cautious route to the official library source instead of guessing.",
        )

    def _looks_like_catalog_query(self, message: str) -> bool:
        if re.search(r"\b(?:97[89][-\s]?)?\d[\d\s-]{8,}\d\b", message):
            return True
        if SERVICE_INTENT_PATTERN.search(message) or ILL_DDS_INTENT_PATTERN.search(message):
            return False
        if POLICY_INTENT_PATTERN.search(message) and not re.search(
            r"\b(do you have|is .+ in the library|find|isbn|author|title|catalog|catalogue)\b",
            message,
            re.IGNORECASE,
        ):
            return False
        return CATALOG_INTENT_PATTERN.search(message) is not None

    def _looks_like_ejournal_query(self, message: str) -> bool:
        if OFF_CAMPUS_INTENT_PATTERN.search(message) or ILL_DDS_INTENT_PATTERN.search(message):
            return False
        return EJOURNAL_INTENT_PATTERN.search(message) is not None

    def _looks_like_repository_query(self, message: str) -> bool:
        if ILL_DDS_INTENT_PATTERN.search(message):
            return False
        if re.search(r"\b(author|paper)\b", message, re.IGNORECASE) and CATALOG_INTENT_PATTERN.search(message):
            return False
        return REPOSITORY_INTENT_PATTERN.search(message) is not None

    def _route_answer_policy(self, route: QueryRoute) -> str:
        source_types = ", ".join(sorted(route.allowed_source_types)) or "all supplied evidence"
        return (
            f"Detected intent: {route.intent}\n"
            f"Allowed evidence source types: {source_types}\n"
            f"{route.policy}"
        ).strip()

    def _format_context_block(self, result: SearchResult) -> str:
        source_label = {
            "faq": "IITGN Library FAQ/policy",
            "catalog": "Library catalog/resource metadata",
            "ejournal": "E-journal/e-resource access metadata",
            "repository_publication": "IITGN repository publication metadata",
            "library_website": "IITGN Library website/service page",
            "live_catalog": "Live Koha catalogue result",
        }.get(result.source_type, result.source_type)
        metadata_lines = [
            f"{key.replace('_', ' ').title()}: {value}"
            for key, value in sorted(result.metadata.items())
        ]
        metadata_text = "\n".join(metadata_lines)
        return (
            f"Evidence source type: {source_label}\n"
            f"Title: {result.title}\n"
            f"Content:\n{result.content}\n"
            f"{metadata_text}\n"
            f"Source: {result.source}"
        ).strip()

    def _rewrite_with_context(self, message: str, recent_turns: list[ChatTurn]) -> str:
        if not recent_turns:
            return message

        stripped = message.strip()
        lowered = stripped.lower()
        message_words = lowered.split()
        if self._has_standalone_intent(stripped):
            return message

        is_short = len(message_words) <= 8
        starts_with_follow_up = message_words[:1] and message_words[0] in FOLLOW_UP_HINTS
        contains_reference = REFERENTIAL_PATTERN.search(stripped) is not None
        ends_with_question_fragment = stripped.endswith("?") and len(message_words) <= 6

        if not (is_short or starts_with_follow_up or contains_reference or ends_with_question_fragment):
            return message

        previous_user_message = recent_turns[-1].user_message
        return f"{previous_user_message} {message}".strip()

    def _has_standalone_intent(self, message: str) -> bool:
        return any(
            pattern.search(message)
            for pattern in (
                HOURS_INTENT_PATTERN,
                PHONE_CALL_PATTERN,
                BORROWING_PATTERN,
                CONTACT_INTENT_PATTERN,
                OFF_CAMPUS_INTENT_PATTERN,
                ILL_DDS_INTENT_PATTERN,
                EJOURNAL_INTENT_PATTERN,
                REPOSITORY_INTENT_PATTERN,
                RULES_INTENT_PATTERN,
                CATALOG_INTENT_PATTERN,
            )
        ) or self._looks_like_catalog_query(message)

    def _expand_query(self, message: str, route: QueryRoute) -> str:
        lowered = message.lower()
        if route.intent == "SERVICE_HOURS":
            return (
                f"{message} library hours timings opening closing Main Library hours "
                "semester Monday Friday Saturday Sunday holidays vacation circulation "
                "Mini-Library 24x7 locations libhours"
            )
        if "call number" not in lowered and PHONE_CALL_PATTERN.search(message):
            return f"{message} take phone calls phone quiet"
        if route.intent == "SERVICE_BORROWING":
            return (
                f"{message} borrow books loan record short loan renew RFID kiosk "
                "circulation issue library borrowing policy"
            )
        if route.intent == "SERVICE_ILL_DDS":
            return (
                f"{message} document delivery service DDS inter library loan ILL article copy "
                "unavailable bibliographic details libraryservices librarycirculation"
            )
        if route.intent == "SERVICE_OFF_CAMPUS":
            return f"{message} off-campus access RemoteXS VPN e-resources IITGN email libraryservices"
        if route.intent == "SERVICE_CONTACT":
            return (
                f"{message} library contact email phone circulation services acquisitions librarian "
                "librarycirculation libraryservices libraryacquisitions"
            )
        if route.intent == "SERVICE_RULES":
            return f"{message} library rules policy food drink phone silence ID card fine fee decorum"
        if route.intent == "EJOURNAL_ACCESS":
            return f"{message} e-journal journal e-resource database access subscription coverage provider collection active"
        if route.intent == "REPOSITORY_PUBLICATION":
            return f"{message} repository publication"
        if route.intent in {"GENERAL_LIBRARY", "UNKNOWN"} and SERVICE_INTENT_PATTERN.search(message):
            if any(token in lowered for token in ("purchase", "recommend", "acquisition", "procurement")):
                return (
                    f"{message} recommend resources purchase subscription books journals "
                    "libraryacquisitions librarian purchase suggestion KOHA"
                )
            if any(token in lowered for token in ("article copy", "document delivery", "dds", "not available")):
                return (
                    f"{message} document delivery service DDS article copy unavailable "
                    "bibliographic details libraryservices"
                )
            if any(token in lowered for token in ("off-campus", "off campus", "remote", "remotexs", "vpn")):
                return f"{message} off-campus access RemoteXS VPN e-resources libraryservices"
            if any(token in lowered for token in ("turnitin", "similarity", "grammarly", "research support")):
                return f"{message} research support Turnitin similarity checking Grammarly libraryservices"
            return (
                f"{message} library services overview help contact circulation borrowing "
                "off-campus access ILL research support Turnitin Grammarly purchase recommendation"
            )
        return message

    def _store(self, session_id: str, user_message: str, result: ChatResult) -> None:
        self.storage.log_message(
            StoredMessage(
                session_id=session_id,
                user_message=user_message,
                assistant_message=result.answer,
                source_url=result.source_url,
                response_mode=result.response_mode,
                confidence=result.confidence,
            )
        )
