"""Export a CSV template for roadview visual review decisions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_review_exports import export_visual_review_decision_csv, load_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = export_visual_review_decision_csv(load_json(args.visual_review_sheet), args.output)
    print(f"visual_review_decisions_csv_output={args.output}")
    print(f"summary=rows:{summary['rows']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--visual-review-sheet",
        type=Path,
        default=Path("data/roadview_visual_review_sheet.json"),
        help="Roadview visual review sheet JSON.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output CSV template.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
