from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import threading
from typing import Any


@dataclass(frozen=True)
class StoredMessage:
    session_id: str
    user_message: str
    assistant_message: str
    source_url: str
    response_mode: str
    confidence: float


@dataclass(frozen=True)
class ChatTurn:
    user_message: str
    assistant_message: str
    source_url: str
    response_mode: str
    confidence: float


class ChatStorage:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    assistant_message TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    response_mode TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    helpful INTEGER NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def log_message(self, message: StoredMessage) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (
                    session_id, user_message, assistant_message, source_url, response_mode, confidence
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.session_id,
                    message.user_message,
                    message.assistant_message,
                    message.source_url,
                    message.response_mode,
                    message.confidence,
                ),
            )

    def log_feedback(self, session_id: str, helpful: bool, comment: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback (session_id, helpful, comment)
                VALUES (?, ?, ?)
                """,
                (session_id, int(helpful), comment.strip()),
            )

    def recent_messages(self, session_id: str, limit: int = 4) -> list[ChatTurn]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_message, assistant_message, source_url, response_mode, confidence
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        turns = [
            ChatTurn(
                user_message=row["user_message"],
                assistant_message=row["assistant_message"],
                source_url=row["source_url"],
                response_mode=row["response_mode"],
                confidence=row["confidence"],
            )
            for row in rows
        ]
        turns.reverse()
        return turns

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            chats = connection.execute("SELECT COUNT(*) AS count FROM chat_messages").fetchone()
            feedback = connection.execute("SELECT COUNT(*) AS count FROM feedback").fetchone()
        return {
            "messages_logged": chats["count"],
            "feedback_logged": feedback["count"],
        }
