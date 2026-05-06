from __future__ import annotations

import unittest

from library_chatbot.catalog import _extract_detail_urls, _parse_detail_page


DETAIL_HTML = """
<html>
  <body>
    <h1>Introduction to the theory of computation</h1>
    <div id="catalogue_detail_biblio">
      <span>By:</span>
      <ul><li>Sipser, Michael</li></ul>
      <span>ISBN:</span>
      <ul><li>9788131525296</li></ul>
    </div>
    <table>
      <tr><th>Item type</th><th>Current library</th><th>Call number</th><th>Status</th><th>Date due</th><th>Barcode</th></tr>
      <tr><td>Books</td><td>IIT Gandhinagar</td><td>004.0151 SIP</td><td>Available</td><td></td><td>12345</td></tr>
    </table>
  </body>
</html>
"""


class CatalogParserTests(unittest.TestCase):
    def test_extract_detail_urls_deduplicates_relative_koha_links(self) -> None:
        html = """
        <a href="/cgi-bin/koha/opac-detail.pl?biblionumber=123">One</a>
        <a href="/cgi-bin/koha/opac-detail.pl?biblionumber=123">Duplicate</a>
        <a href="/cgi-bin/koha/opac-detail.pl?biblionumber=456&amp;query_desc=sipser">Two</a>
        """
        urls = _extract_detail_urls(html, "https://catalog.iitgn.ac.in")
        self.assertEqual(
            urls,
            [
                "https://catalog.iitgn.ac.in/cgi-bin/koha/opac-detail.pl?biblionumber=123",
                "https://catalog.iitgn.ac.in/cgi-bin/koha/opac-detail.pl?biblionumber=456&query_desc=sipser",
            ],
        )

    def test_parse_detail_page_extracts_core_record_fields(self) -> None:
        record = _parse_detail_page(
            DETAIL_HTML,
            "https://catalog.iitgn.ac.in/cgi-bin/koha/opac-detail.pl?biblionumber=123",
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.title, "Introduction to the theory of computation")
        self.assertEqual(record.authors, "Sipser, Michael")
        self.assertEqual(record.isbn, "9788131525296")
        self.assertEqual(record.item_type, "Books")
        self.assertEqual(record.call_number, "004.0151 SIP")
        self.assertEqual(record.status, "Available")
        self.assertEqual(record.barcode, "12345")


if __name__ == "__main__":
    unittest.main()
