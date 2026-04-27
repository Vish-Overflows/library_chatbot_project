from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from library_chatbot.knowledge_base import KnowledgeBase


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.csv_path = temp_path / "faqs.csv"
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Questions", "Answers"])
            writer.writeheader()
            writer.writerow(
                {
                    "Questions": "What are the library hours?",
                    "Answers": "The library is open 9 AM to 8 PM.",
                }
            )
            writer.writerow(
                {
                    "Questions": "Where is the library located?",
                    "Answers": "The library is in Block 13.",
                }
            )
        self.catalog_path = temp_path / "catalog.csv"
        with self.catalog_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "Title",
                    "Author",
                    "ISBN",
                    "Subject",
                    "Call Number",
                    "Location",
                    "Availability",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Title": "Introduction to Algorithms",
                    "Author": "Thomas H. Cormen",
                    "ISBN": "9780262046305",
                    "Subject": "Algorithms; Computer Science",
                    "Call Number": "QA76.6 I58",
                    "Location": "Main Library - Computer Science shelves",
                    "Availability": "Available",
                }
            )
        self.ejournal_path = temp_path / "ejournals.csv"
        with self.ejournal_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "publication_title",
                    "issn",
                    "publisher_name",
                    "publication_type",
                    "title_url",
                    "provider_name",
                    "collectionname",
                    "active_or_inactive_y",
                    "coverage_y",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "publication_title": "ACM Computing Surveys",
                    "issn": "0360-0300",
                    "publisher_name": "Association for Computing Machinery",
                    "publication_type": "serial",
                    "title_url": "https://dl.acm.org/loi/csur",
                    "provider_name": "ONOS",
                    "collectionname": "ACM Digital Library",
                    "active_or_inactive_y": "Active",
                    "coverage_y": "1969-2026",
                }
            )
            writer.writerow(
                {
                    "publication_title": "Journal of Fluid Mechanics",
                    "issn": "0022-1120",
                    "publisher_name": "Cambridge University Press",
                    "publication_type": "serial",
                    "title_url": "https://www.cambridge.org/core/journals/journal-of-fluid-mechanics",
                    "provider_name": "ONOS",
                    "collectionname": "Cambridge University Press Journals",
                    "active_or_inactive_y": "Active",
                    "coverage_y": "1956-2026",
                }
            )
            writer.writerow(
                {
                    "publication_title": "Library Trends",
                    "issn": "0024-2594",
                    "publisher_name": "Johns Hopkins University Press",
                    "publication_type": "serial",
                    "title_url": "https://muse.jhu.edu/journal/334",
                    "provider_name": "ONOS",
                    "collectionname": "Project Muse",
                    "active_or_inactive_y": "Active",
                    "coverage_y": "1980-2026",
                }
            )
        self.repository_path = temp_path / "publications.csv"
        with self.repository_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "dc.title",
                    "dc.contributor.author",
                    "dc.identifier.doi",
                    "dc.identifier.uri",
                    "dc.type",
                    "dc.subject",
                    "location.coll",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "dc.title": "Human-centered explainable AI for brain-computer interface-driven rehabilitation",
                    "dc.contributor.author": "Rajpura, Param",
                    "dc.identifier.doi": "10.1145/3772363.3799222",
                    "dc.identifier.uri": "https://repository.iitgn.ac.in/handle/IITG2025/35132",
                    "dc.type": "Conference Paper",
                    "dc.subject": "Explainable AI||Brain-computer interfaces",
                    "location.coll": "Cognitive and Brain Sciences",
                }
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_returns_best_match_first(self) -> None:
        kb = KnowledgeBase.from_csv(self.csv_path)
        results = kb.search("Tell me the library hours", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].question, "What are the library hours?")

    def test_related_questions_skips_identical_question(self) -> None:
        kb = KnowledgeBase.from_csv(self.csv_path)
        related = kb.related_questions("Where is the library located?", limit=2)
        self.assertNotIn("Where is the library located?", related)

    def test_catalog_records_are_searchable_by_title(self) -> None:
        kb = KnowledgeBase.from_sources(self.csv_path, [self.catalog_path])
        results = kb.search("Where is Introduction to Algorithms?", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].source_type, "catalog")
        self.assertIn("Computer Science shelves", results[0].content)

    def test_catalog_records_are_searchable_by_isbn(self) -> None:
        kb = KnowledgeBase.from_sources(self.csv_path, [self.catalog_path])
        results = kb.search("9780262046305", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].metadata["isbn"], "9780262046305")

    def test_ejournal_records_are_typed_and_searchable(self) -> None:
        kb = KnowledgeBase.from_sources(self.csv_path, [self.ejournal_path])
        results = kb.search("Do we have access to ACM Computing Surveys?", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].source_type, "ejournal")
        self.assertEqual(results[0].metadata["coverage"], "1969-2026")
        self.assertIn("ACM Digital Library", results[0].content)

    def test_subject_journal_query_does_not_overweight_library_word(self) -> None:
        kb = KnowledgeBase.from_sources(self.csv_path, [self.ejournal_path])
        results = kb.search("what journals does the library have on statics and fluids", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].title, "Journal of Fluid Mechanics")

    def test_repository_records_are_typed_and_searchable(self) -> None:
        kb = KnowledgeBase.from_sources(self.csv_path, [self.repository_path])
        results = kb.search("Human-centered explainable AI rehabilitation", limit=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].source_type, "repository_publication")
        self.assertEqual(results[0].metadata["doi"], "10.1145/3772363.3799222")


if __name__ == "__main__":
    unittest.main()
