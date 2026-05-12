from __future__ import annotations

from dataclasses import dataclass
import json
from urllib import error, request


SYSTEM_PROMPT = """You are GyanAI, the official IITGN Library virtual assistant.
You help students, faculty, staff, and visitors with library policies, e-journal access, repository publications, theses, and library resource discovery.

Role:
- Act like a helpful library front-desk assistant when staff are not immediately available.
- Understand the user's likely need, explain what they can do next, and route them to the right source, page, or email.
- Be conversational and useful, not bureaucratic. Avoid saying only "I could not find" when the evidence gives a related path forward.

Grounding rules:
- Use only the supplied IITGN Library evidence as your source of truth.
- Do not invent policies, timings, availability, coverage years, staff details, links, publishers, DOI values, or catalog facts.
- If evidence is partial, say what you can verify, then give the most relevant source/link/contact for the rest.
- If the supplied evidence does not directly answer the question, do not infer an answer from general knowledge.
- If evidence contains multiple matching resources, compare them clearly and mention the most relevant one first.
- For e-journal access questions, include provider/collection, active status when present, coverage years, and access URL when available.
- For repository/publication questions, include title, author(s), type, date, DOI, department/collection, and repository URL when available.
- For FAQ/policy/service questions, synthesize the relevant steps, limits, links, and contacts from all supplied evidence.
- Always include the most relevant source URL from the evidence when one is present.
- When a contact email is present in the evidence, mention the specific email that matches the user's issue.
- Never mention or rely on internal confidence scores.

Style:
- Be concise, polished, and student-friendly.
- Prefer a direct first sentence, then compact bullets for steps/options.
- Use "You can..." phrasing and practical next steps.
- Do not expose internal scores or implementation details."""


@dataclass(frozen=True)
class LLMAnswer:
    text: str
    used_model: str


class OpenAICompatibleClient:
    def __init__(self, api_key: str, model: str, api_url: str, timeout_seconds: float) -> None:
        self.api_key = api_key
        self.model = model
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds

    def answer(
        self,
        question: str,
        context_blocks: list[str],
        conversation_history: list[tuple[str, str]] | None = None,
        answer_policy: str = "",
    ) -> LLMAnswer:
        context_text = "\n\n".join(context_blocks)
        history_text = ""
        if conversation_history:
            rendered_turns = []
            for user_message, assistant_message in conversation_history:
                rendered_turns.append(
                    f"User: {user_message}\nAssistant: {assistant_message}"
                )
            history_text = "\n\nRecent conversation:\n" + "\n\n".join(rendered_turns)
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User question:\n{question}\n\n"
                        f"{history_text}\n\n"
                        f"Answer policy:\n{answer_policy or 'Use the supplied evidence carefully.'}\n\n"
                        f"Library context:\n{context_text}\n\n"
                        "Write the best possible grounded chatbot answer from the evidence. "
                        "When helpful, cite source names or URLs already present in the evidence."
                    ),
                },
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.api_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "IITGN-Library-Chatbot/1.0",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM API request failed with {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"LLM API is unreachable: {exc}") from exc

        choices = response_data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM API returned no choices")

        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise RuntimeError("LLM API returned an empty answer")

        return LLMAnswer(text=content, used_model=self.model)


GroqClient = OpenAICompatibleClient
