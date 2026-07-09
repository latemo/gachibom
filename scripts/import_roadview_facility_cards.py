"""Import Jeju social-vulnerable roadview facility status CSV."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.catalog import import_catalog_rows, summarize_catalog, write_catalog_json
from src.catalog_providers import SourceDefaults, normalize_public_place_rows
from src.roadview_data import (
    FACILITY_STATUS_SOURCE_URL,
    facility_rows_to_accessibility_cards,
    load_csv_rows,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checked_at = date.fromisoformat(args.checked_at)
    rows = load_csv_rows(args.input, encoding=args.encoding)
    cards = facility_rows_to_accessibility_cards(rows, checked_at=checked_at, source_url=args.source_url)
    write_json(cards, args.output_cards)

    print(f"cards_output={args.output_cards}")
    print(f"cards_imported={len(cards)}")

    if args.output_catalog:
        source = SourceDefaults(
            source_name="제주특별자치도",
            source_url=args.source_url,
            dataset_name="사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
            license="이용허락범위 제한 없음",
            source_updated_at=args.source_updated_at,
        )
        normalized_rows = normalize_public_place_rows(rows, source_defaults=source, default_category="other")
        items = import_catalog_rows(
            [row for row in normalized_rows if row["name"]],
            imported_at=checked_at,
            accessibility_cards=load_accessibility_cards(args.accessibility_cards),
        )
        write_catalog_json(items, args.output_catalog)
        summary = summarize_catalog(items)
        print(f"catalog_output={args.output_catalog}")
        print(
            "catalog_summary="
            f"imported:{summary.imported}, "
            f"matched:{summary.matched}, "
            f"candidates:{summary.candidates}, "
            f"unmatched:{summary.unmatched}"
        )

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="15109153 facility status CSV path.")
    parser.add_argument("--output-cards", type=Path, required=True, help="Output accessibility card draft JSON.")
    parser.add_argument("--output-catalog", type=Path, help="Optional raw place catalog JSON output.")
    parser.add_argument("--accessibility-cards", type=Path, help="Existing accessibility cards for catalog matching.")
    parser.add_argument("--source-url", default=FACILITY_STATUS_SOURCE_URL, help="Source dataset URL.")
    parser.add_argument("--source-updated-at", default="2025-07-30", help="Source updated date in YYYY-MM-DD.")
    parser.add_argument("--checked-at", required=True, help="Import/check date in YYYY-MM-DD.")
    parser.add_argument("--encoding", default="utf-8-sig", help="CSV encoding.")
    return parser.parse_args(argv)


def load_accessibility_cards(path: Path | None) -> list[dict]:
    if not path:
        return []
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
