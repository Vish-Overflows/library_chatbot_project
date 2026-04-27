from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import csv

from library_chatbot.knowledge_base import (
    CATALOG_COLUMN_ALIASES,
    FAQ_SOURCE,
    KnowledgeBase,
    _read_xlsx_rows,
    _normalize_column_name,
)


def normalized_headers(path: Path) -> list[str]:
    if path.suffix.lower() == ".xlsx":
        rows = _read_xlsx_rows(path)
        if not rows:
            return []
        return [_normalize_column_name(header) for header in rows[0]]

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [_normalize_column_name(header) for header in reader.fieldnames or []]


def matching_fields(headers: list[str]) -> dict[str, list[str]]:
    header_set = set(headers)
    matches: dict[str, list[str]] = {}
    for canonical_name, aliases in CATALOG_COLUMN_ALIASES.items():
        matched_aliases = [alias for alias in aliases if alias in header_set]
        if matched_aliases:
            matches[canonical_name] = matched_aliases
    return matches


def print_catalog_report(path: Path) -> None:
    headers = normalized_headers(path)
    matches = matching_fields(headers)
    documents = KnowledgeBase._load_catalog(path)
    skipped_rows = max(0, count_data_rows(path) - len(documents))

    print(f"Catalog: {path}")
    print(f"  Headers detected: {', '.join(headers) if headers else 'none'}")
    print(f"  Usable records: {len(documents)}")
    print(f"  Skipped rows without title: {skipped_rows}")
    print("  Recognized fields:")
    for field_name in CATALOG_COLUMN_ALIASES:
        aliases = matches.get(field_name, [])
        value = ", ".join(aliases) if aliases else "not found"
        print(f"    - {field_name}: {value}")

    if documents:
        print("  Sample parsed records:")
        for document in documents[:3]:
            metadata = ", ".join(f"{key}={value}" for key, value in document.metadata.items())
            print(f"    - {document.title} ({metadata})")
    print()


def count_data_rows(path: Path) -> int:
    if path.suffix.lower() == ".xlsx":
        rows = _read_xlsx_rows(path)
        return max(0, len(rows) - 1)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def validate_sources(faq_path: Path, catalog_paths: list[Path]) -> int:
    knowledge_base = KnowledgeBase.from_sources(faq_path=faq_path, catalog_paths=catalog_paths)
    source_counts = Counter(document.source_type for document in knowledge_base.documents)
    catalog_record_count = sum(
        count
        for source_type, count in source_counts.items()
        if source_type != FAQ_SOURCE
    )

    print("Knowledge base validation")
    print(f"  FAQ path: {faq_path}")
    print(f"  FAQ records: {source_counts.get(FAQ_SOURCE, 0)}")
    print(f"  Catalog/resource records: {catalog_record_count}")
    print(f"  Source type counts: {dict(source_counts)}")
    print(f"  Total documents: {len(knowledge_base.documents)}")
    print()

    for catalog_path in catalog_paths:
        print_catalog_report(catalog_path)

    if source_counts.get(FAQ_SOURCE, 0) == 0:
        print("ERROR: no FAQ records loaded.")
        return 1
    if catalog_paths and catalog_record_count == 0:
        print("ERROR: catalog/resource paths were provided, but no records loaded.")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate FAQ and catalog metadata before running the chatbot."
    )
    parser.add_argument("--faq", type=Path, default=Path("FAQs.csv"), help="Path to FAQ CSV.")
    parser.add_argument(
        "--catalog",
        type=Path,
        action="append",
        default=[],
        help="Path to a catalog/resource metadata CSV. Repeat for multiple files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(validate_sources(args.faq, args.catalog))


if __name__ == "__main__":
    main()
