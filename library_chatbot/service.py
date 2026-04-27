from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import uuid4

from library_chatbot.knowledge_base import KnowledgeBase, SearchResult
from library_chatbot.llm import OpenAICompatibleClient
from library_chatbot.storage import ChatStorage, ChatTurn, StoredMessage


GREETING_RESPONSES = {
    "hi": "Hello! How can I help you with IITGN Library today?",
    "hello": "Hello! How can I help you with IITGN Library today?",
    "hey": "Hello! How can I help you with IITGN Library today?",
}

FALLBACK_ANSWER = (
    "I could not find a reliable answer in the current library knowledge base. "
    "Please try rephrasing your question or contact the library at librarian@iitgn.ac.in."
)
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


class ChatService:
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        storage: ChatStorage,
        similarity_threshold: float,
        top_k: int,
        conversation_history_limit: int,
        llm_client: OpenAICompatibleClient | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.storage = storage
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.conversation_history_limit = conversation_history_limit
        self.llm_client = llm_client

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

        effective_query = self._rewrite_with_context(clean_message, recent_turns)
        search_results = self.knowledge_base.search(effective_query, limit=self.top_k)
        if not search_results or search_results[0].score < self.similarity_threshold:
            if effective_query != clean_message:
                direct_results = self.knowledge_base.search(clean_message, limit=self.top_k)
                if direct_results and direct_results[0].score > (search_results[0].score if search_results else 0.0):
                    search_results = direct_results
                    effective_query = clean_message

            result = ChatResult(
                session_id=session,
                answer=FALLBACK_ANSWER,
                source_url="https://library.iitgn.ac.in/",
                sources=self._source_citations(search_results),
                related_questions=self.knowledge_base.related_questions(effective_query, limit=3),
                response_mode="fallback",
                confidence=search_results[0].score if search_results else 0.0,
            )
            self._store(session, clean_message, result)
            return result

        top_result = search_results[0]
        answer_text, response_mode = self._compose_answer(clean_message, effective_query, search_results, recent_turns)
        if effective_query != clean_message and response_mode == "retrieval":
            response_mode = "contextual_retrieval"
        result = ChatResult(
            session_id=session,
            answer=answer_text,
            source_url=top_result.source,
            sources=self._source_citations(search_results),
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
    ) -> tuple[str, str]:
        top_result = search_results[0]
        if self.llm_client is None:
            return top_result.answer, "retrieval"

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
            )
            return llm_answer.text, "llm"
        except RuntimeError:
            return top_result.answer, "retrieval"

    def _source_citations(self, search_results: list[SearchResult]) -> list[SourceCitation]:
        citations: list[SourceCitation] = []
        for result in search_results[:5]:
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

    def _format_context_block(self, result: SearchResult) -> str:
        source_label = {
            "faq": "IITGN Library FAQ/policy",
            "catalog": "Library catalog/resource metadata",
            "ejournal": "E-journal/e-resource access metadata",
            "repository_publication": "IITGN repository publication metadata",
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
        is_short = len(message_words) <= 8
        starts_with_follow_up = message_words[:1] and message_words[0] in FOLLOW_UP_HINTS
        contains_reference = REFERENTIAL_PATTERN.search(stripped) is not None
        ends_with_question_fragment = stripped.endswith("?") and len(message_words) <= 6

        if not (is_short or starts_with_follow_up or contains_reference or ends_with_question_fragment):
            return message

        previous_user_message = recent_turns[-1].user_message
        return f"{previous_user_message} {message}".strip()

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
