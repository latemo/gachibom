"""Merge place-level roadview visual review decision CSV files into the master CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_review_exports import merge_visual_review_decision_csvs


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = merge_visual_review_decision_csvs(args.csv_dir, args.output)
    print(f"visual_review_decisions_csv_output={args.output}")
    print(f"summary=files:{summary['files']}, rows:{summary['rows']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("data/roadview_visual_review_decisions_by_place"),
        help="Directory containing place-level CSV files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/roadview_visual_review_decisions.csv"),
        help="Merged master CSV output.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
