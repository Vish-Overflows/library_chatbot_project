from __future__ import annotations

from pathlib import Path
from collections import Counter

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from library_chatbot.config import get_settings
from library_chatbot.knowledge_base import KnowledgeBase
from library_chatbot.llm import OpenAICompatibleClient
from library_chatbot.service import ChatService
from library_chatbot.storage import ChatStorage


load_dotenv()
settings = get_settings()

knowledge_base = KnowledgeBase.from_sources(
    faq_path=settings.faq_path,
    catalog_paths=settings.catalog_paths,
)
storage = ChatStorage(settings.database_path)
llm_client = None
if settings.llm_api_key:
    llm_client = OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        api_url=settings.llm_api_url,
        timeout_seconds=settings.request_timeout_seconds,
    )

chat_service = ChatService(
    knowledge_base=knowledge_base,
    storage=storage,
    similarity_threshold=settings.similarity_threshold,
    top_k=settings.top_k,
    conversation_history_limit=settings.conversation_history_limit,
    llm_client=llm_client,
)

app = FastAPI(title=settings.app_name)

allow_credentials = settings.allowed_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if settings.allowed_origins else ["*"],
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _static_dir() -> Path:
    configured_dir = Path(settings.static_dir)
    fallback_dir = Path(__file__).resolve().parent / "static"
    if (configured_dir / "index.html").exists():
        return configured_dir
    return fallback_dir


STATIC_DIR = _static_dir()
INDEX_PATH = STATIC_DIR / "index.html"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    source_url: str
    sources: list["SourceResponse"]
    related_questions: list[str]
    response_mode: str
    confidence: float


class SourceResponse(BaseModel):
    title: str
    source_type: str
    source_url: str
    confidence: float
    metadata: dict[str, str]


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    helpful: bool
    comment: str = Field(default="", max_length=1000)


@app.get("/api/health")
def healthcheck() -> dict[str, object]:
    source_counts = Counter(document.source_type for document in knowledge_base.documents)
    return {
        "status": "ok",
        "knowledge_documents": len(knowledge_base.documents),
        "knowledge_sources": dict(source_counts),
        "catalog_sources": [str(path) for path in settings.catalog_paths],
        "llm_enabled": llm_client is not None,
        "storage": storage.stats(),
    }


@app.get("/api/static-health")
def static_healthcheck() -> dict[str, object]:
    configured_dir = Path(settings.static_dir)
    fallback_dir = Path(__file__).resolve().parent / "static"
    return {
        "configured_static_dir": str(configured_dir),
        "configured_index_exists": (configured_dir / "index.html").exists(),
        "served_static_dir": str(STATIC_DIR),
        "served_index_exists": INDEX_PATH.exists(),
        "static_files": sorted(path.name for path in STATIC_DIR.glob("*") if path.is_file()),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = chat_service.answer(request.message, request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ChatResponse(
        session_id=result.session_id,
        answer=result.answer,
        source_url=result.source_url,
        sources=[
            SourceResponse(
                title=source.title,
                source_type=source.source_type,
                source_url=source.source_url,
                confidence=source.confidence,
                metadata=source.metadata,
            )
            for source in result.sources
        ],
        related_questions=result.related_questions,
        response_mode=result.response_mode,
        confidence=result.confidence,
    )


@app.post("/api/feedback")
def feedback(request: FeedbackRequest) -> dict[str, str]:
    storage.log_feedback(request.session_id, request.helpful, request.comment)
    return {"status": "saved"}


@app.get("/")
@app.get("/app")
def index() -> FileResponse:
    if not INDEX_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"UI entrypoint not found at {INDEX_PATH}",
        )
    return FileResponse(INDEX_PATH)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
