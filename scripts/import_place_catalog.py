"""Import public Jeju place CSV data into the internal place catalog JSON."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.catalog import import_catalog_rows, summarize_catalog, write_catalog_json
from src.catalog_providers import SourceDefaults, normalize_public_place_rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    imported_at = date.fromisoformat(args.imported_at) if args.imported_at else date.today()
    source_defaults = SourceDefaults(
        source_name=args.source_name,
        source_url=args.source_url,
        dataset_name=args.dataset_name,
        license=args.license,
        source_updated_at=args.source_updated_at,
    )

    with args.input.open("r", encoding=args.encoding, newline="") as handle:
        raw_rows = list(csv.DictReader(handle))

    normalized_rows = normalize_public_place_rows(
        raw_rows,
        source_defaults=source_defaults,
        default_category=args.default_category,
    )
    skipped = len([row for row in normalized_rows if not row["name"]])
    normalized_rows = [row for row in normalized_rows if row["name"]]
    accessibility_cards = load_accessibility_cards(args.accessibility_cards)

    items = import_catalog_rows(
        normalized_rows,
        imported_at=imported_at,
        accessibility_cards=accessibility_cards,
    )
    write_catalog_json(items, args.output)

    summary = summarize_catalog(items)
    print(f"output={args.output}")
    print(
        "summary="
        f"imported:{summary.imported}, "
        f"matched:{summary.matched}, "
        f"candidates:{summary.candidates}, "
        f"unmatched:{summary.unmatched}, "
        f"skipped:{skipped}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source CSV path.")
    parser.add_argument("--output", type=Path, required=True, help="Output catalog JSON path.")
    parser.add_argument("--source-name", required=True, help="Public data provider name.")
    parser.add_argument("--source-url", required=True, help="Dataset or API detail URL.")
    parser.add_argument("--dataset-name", required=True, help="Source dataset name.")
    parser.add_argument("--license", default="unknown", help="Source license label.")
    parser.add_argument("--source-updated-at", help="Source updated date in YYYY-MM-DD.")
    parser.add_argument("--default-category", help="Fallback category when the source has no category column.")
    parser.add_argument("--accessibility-cards", type=Path, help="Accessibility card JSON path for matching.")
    parser.add_argument("--encoding", default="utf-8-sig", help="CSV encoding.")
    parser.add_argument("--imported-at", help="Import date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


def load_accessibility_cards(path: Path | None) -> list[dict]:
    if not path:
        return []
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
