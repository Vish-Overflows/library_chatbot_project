from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _split_csv_env(name: str, default: str = "") -> list[str]:
    raw_value = os.getenv(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str
    faq_path: Path
    catalog_paths: list[Path]
    database_path: Path
    static_dir: Path
    llm_api_key: str | None
    llm_model: str
    llm_api_url: str
    request_timeout_seconds: float
    top_k: int
    similarity_threshold: float
    conversation_history_limit: int
    allowed_origins: list[str]


def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parent.parent
    return Settings(
        app_name=os.getenv("APP_NAME", "IITGN Library Chatbot"),
        faq_path=Path(os.getenv("FAQ_PATH", root_dir / "FAQs.csv")),
        catalog_paths=[Path(path) for path in _split_csv_env("CATALOG_PATHS", "")],
        database_path=Path(os.getenv("DATABASE_PATH", root_dir / "instance" / "chatbot.db")),
        static_dir=Path(os.getenv("STATIC_DIR", root_dir / "static")),
        llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("XAI_API_KEY") or os.getenv("GROQ_API_KEY"),
        llm_model=os.getenv("LLM_MODEL") or os.getenv("XAI_MODEL") or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        llm_api_url=os.getenv(
            "LLM_API_URL",
            os.getenv(
                "XAI_API_URL",
                os.getenv(
                    "GROQ_API_URL",
                    "https://api.groq.com/openai/v1/chat/completions",
                ),
            ),
        ),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        top_k=max(1, int(os.getenv("TOP_K", "4"))),
        similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.18")),
        conversation_history_limit=max(1, int(os.getenv("CONVERSATION_HISTORY_LIMIT", "4"))),
        allowed_origins=_split_csv_env("ALLOWED_ORIGINS", "*"),
    )
