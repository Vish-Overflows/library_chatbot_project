from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from library_chatbot.knowledge_base import KnowledgeBase
from library_chatbot.catalog import CatalogRecord, CatalogSearchResult
from library_chatbot.llm import LLMAnswer
from library_chatbot.service import ChatService
from library_chatbot.storage import ChatStorage


class RecordingLLM:
    def __init__(self) -> None:
        self.calls = 0

    def answer(self, **_: object) -> LLMAnswer:
        self.calls += 1
        return LLMAnswer(text="Generated from grounded evidence.", used_model="test-model")


class FakeCatalogClient:
    def __init__(self, result: CatalogSearchResult) -> None:
        self.result = result
        self.queries: list[str] = []

    def search(self, query: str) -> CatalogSearchResult:
        self.queries.append(query)
        return self.result


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

        website_path = temp_path / "website.csv"
        with website_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["title", "description", "source", "source_type", "subject"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "title": "Library hours and locations",
                    "description": (
                        "Main Library hours during semester: Monday to Friday 9.00 a.m. "
                        "to 2.00 a.m.; Saturday, Sunday, and holidays 9.00 a.m. to "
                        "12.00 a.m. Mini-Library is open all days 24x7."
                    ),
                    "source": "https://library.iitgn.ac.in/libhours.php",
                    "source_type": "library_website",
                    "subject": "hours timing opening circulation location mini library main library",
                }
            )

        repository_path = temp_path / "repository.csv"
        with repository_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["dc_title", "dc_identifier_uri", "dc_type", "dc_subject"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "dc_title": "Some qualitative questions on the equation",
                    "dc_identifier_uri": "https://repository.iitgn.ac.in/handle/IITG2025/21783",
                    "dc_type": "Article",
                    "dc_subject": "Mathematics",
                }
            )

        database_path = temp_path / "chatbot.db"
        self.service = ChatService(
            knowledge_base=KnowledgeBase.from_sources(
                faq_path,
                [catalog_path, website_path, repository_path],
            ),
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

    def test_moderate_confidence_match_uses_grounded_generation(self) -> None:
        llm = RecordingLLM()
        self.service.llm_client = llm
        result = self.service.answer("available learning")
        self.assertEqual(result.response_mode, "llm")
        self.assertEqual(result.answer, "Generated from grounded evidence.")
        self.assertEqual(llm.calls, 1)

    def test_high_confidence_match_can_use_grounded_generation(self) -> None:
        llm = RecordingLLM()
        self.service.llm_client = llm
        result = self.service.answer("9780262035613")
        self.assertEqual(result.response_mode, "llm")
        self.assertEqual(result.answer, "Generated from grounded evidence.")
        self.assertEqual(llm.calls, 1)

    def test_unknown_catalog_question_redirects_to_catalog(self) -> None:
        result = self.service.answer("Is the parking handbook book available?")
        self.assertEqual(result.response_mode, "fallback")
        self.assertEqual(result.source_url, "https://catalog.iitgn.ac.in/")
        self.assertIn("Relevant source", result.answer)

    def test_library_timings_query_uses_hours_source_not_repository_noise(self) -> None:
        result = self.service.answer("can u gimme library timings")
        self.assertIn("Monday to Friday", result.answer)
        self.assertEqual(result.source_url, "https://library.iitgn.ac.in/libhours.php")
        self.assertTrue(result.sources)
        self.assertTrue(all(source.source_type in {"faq", "library_website"} for source in result.sources))

    def test_live_catalog_search_answers_book_availability(self) -> None:
        catalog_result = CatalogSearchResult(
            query="sipser",
            search_url="https://catalog.iitgn.ac.in/cgi-bin/koha/opac-search.pl?q=sipser",
            records=[
                CatalogRecord(
                    title="Introduction to the theory of computation",
                    authors="Sipser, Michael",
                    call_number="004.0151 SIP",
                    status="Available",
                    item_type="Books",
                    source_url="https://catalog.iitgn.ac.in/cgi-bin/koha/opac-detail.pl?biblionumber=1",
                    confidence=0.9,
                )
            ],
        )
        fake_catalog = FakeCatalogClient(catalog_result)
        self.service.catalog_client = fake_catalog
        result = self.service.answer("is sipser in the library?")
        self.assertEqual(result.response_mode, "live_catalog")
        self.assertIn("Introduction to the theory of computation", result.answer)
        self.assertIn("Available", result.answer)
        self.assertEqual(result.sources[0].source_type, "live_catalog")
        self.assertEqual(fake_catalog.queries, ["sipser"])

    def test_live_catalog_uncertain_result_redirects_to_catalog_search(self) -> None:
        catalog_result = CatalogSearchResult(
            query="spaceship manual",
            search_url="https://catalog.iitgn.ac.in/cgi-bin/koha/opac-search.pl?q=spaceship+manual",
            records=[],
        )
        self.service.catalog_client = FakeCatalogClient(catalog_result)
        result = self.service.answer("do you have spaceship manual?")
        self.assertEqual(result.response_mode, "catalog_redirect")
        self.assertEqual(result.source_url, catalog_result.search_url)
        self.assertIn("search the catalogue directly", result.answer)


if __name__ == "__main__":
    unittest.main()
