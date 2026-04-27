from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from library_chatbot.ingest import matching_fields, validate_sources


class IngestTests(unittest.TestCase):
    def test_matching_fields_recognizes_column_aliases(self) -> None:
        matches = matching_fields(["book_title", "creator", "isbn13", "shelfmark"])
        self.assertEqual(matches["title"], ["book_title"])
        self.assertEqual(matches["authors"], ["creator"])
        self.assertEqual(matches["isbn"], ["isbn13"])
        self.assertEqual(matches["call_number"], ["shelfmark"])

    def test_validate_sources_accepts_faq_and_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            faq_path = temp_path / "faqs.csv"
            catalog_path = temp_path / "catalog.csv"

            with faq_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Questions", "Answers"])
                writer.writeheader()
                writer.writerow({"Questions": "Where is the library?", "Answers": "Block 13."})

            with catalog_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["book_title", "creator", "isbn13"])
                writer.writeheader()
                writer.writerow(
                    {
                        "book_title": "Clean Code",
                        "creator": "Robert C. Martin",
                        "isbn13": "9780132350884",
                    }
                )

            self.assertEqual(validate_sources(faq_path, [catalog_path]), 0)


if __name__ == "__main__":
    unittest.main()
