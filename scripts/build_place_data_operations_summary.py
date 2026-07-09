"""Build the place data operations summary."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.place_data_operations import build_place_data_operations_summary, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    summary = build_place_data_operations_summary(
        load_json(args.places),
        load_json(args.situation_rules),
        raw_catalog_items=load_json(args.raw_catalog) if args.raw_catalog else None,
        generated_at=generated_at,
    )
    write_json(summary, args.output)
    print(f"place_data_operations_summary_output={args.output}")
    print(
        "summary="
        f"total:{summary['summary']['total_places']}, "
        f"public_candidates:{summary['summary']['public_candidate_places']}, "
        f"review_only:{summary['summary']['review_only_places']}, "
        f"raw_catalog:{summary['raw_catalog']['total_items']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--places",
        type=Path,
        default=Path("data/jeju_accessible_spots.json"),
        help="Accessibility place cards JSON.",
    )
    parser.add_argument(
        "--situation-rules",
        type=Path,
        default=Path("data/situation_rules.json"),
        help="Situation rules JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/place_data_operations_summary.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--raw-catalog",
        type=Path,
        help="Optional raw place catalog JSON to summarize alongside accessibility cards.",
    )
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
