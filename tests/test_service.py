from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from library_chatbot.knowledge_base import KnowledgeBase
from library_chatbot.service import ChatService
from library_chatbot.storage import ChatStorage


class ChatServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)

        faq_path = temp_path / "faqs.csv"
        with faq_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Questions", "Answers"])
            writer.writeheader()
            writer.writerow(
                {
                    "Questions": "Can I take phone calls in the library?",
                    "Answers": "No. Please step outside for phone calls and keep the library quiet.",
                }
            )
            writer.writerow(
                {
                    "Questions": "Can I bring food into the library?",
                    "Answers": "No. Outside food should be avoided in the library.",
                }
            )
        catalog_path = temp_path / "catalog.csv"
        with catalog_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["title", "authors", "isbn", "subjects", "location", "availability"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "title": "Deep Learning",
                    "authors": "Ian Goodfellow; Yoshua Bengio; Aaron Courville",
                    "isbn": "9780262035613",
                    "subjects": "Machine Learning; Neural Networks",
                    "location": "Main Library - AI and Data Science shelves",
                    "availability": "Checked out",
                }
            )

        database_path = temp_path / "chatbot.db"
        self.service = ChatService(
            knowledge_base=KnowledgeBase.from_sources(faq_path, [catalog_path]),
            storage=ChatStorage(database_path),
            similarity_threshold=0.2,
            top_k=4,
            conversation_history_limit=4,
            llm_client=None,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_phone_call_query_matches_etiquette_entry(self) -> None:
        result = self.service.answer("Can I call someone inside the library?")
        self.assertIn("phone", result.answer.lower())

    def test_food_query_matches_food_entry(self) -> None:
        result = self.service.answer("Can I bring food?")
        self.assertIn("food", result.answer.lower())

    def test_follow_up_query_uses_previous_turn_context(self) -> None:
        first = self.service.answer("Can I take phone calls in the library?")
        follow_up = self.service.answer("What about that on weekends?", session_id=first.session_id)
        self.assertIn("phone", follow_up.answer.lower())
        self.assertEqual(follow_up.response_mode, "contextual_retrieval")

    def test_catalog_query_returns_grounded_book_record(self) -> None:
        result = self.service.answer("Is Deep Learning available?")
        self.assertIn("Checked out", result.answer)
        self.assertIn("AI and Data Science shelves", result.answer)


if __name__ == "__main__":
    unittest.main()
