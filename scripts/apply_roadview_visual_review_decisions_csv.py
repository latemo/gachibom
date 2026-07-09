"""Apply roadview visual review decisions from CSV to the review sheet JSON."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_review_exports import apply_visual_review_decision_csv, load_json
from src.roadview_image_download import write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    reviewed_at = date.fromisoformat(args.reviewed_at) if args.reviewed_at else generated_at
    result = apply_visual_review_decision_csv(
        load_json(args.visual_review_sheet),
        args.decisions_csv,
        reviewer=args.reviewer,
        reviewed_at=reviewed_at,
        generated_at=generated_at,
    )
    write_json(result["updated_visual_review_sheet"], args.output)
    write_json(result["import_report"], args.report_output)
    summary = result["import_report"]["summary"]
    print(f"visual_review_sheet_output={args.output}")
    print(f"visual_review_decision_import_report_output={args.report_output}")
    print(
        "summary="
        f"rows:{summary['total_rows']}, "
        f"applied:{summary['applied']}, "
        f"skipped:{summary['skipped']}, "
        f"invalid:{summary['invalid']}"
    )
    return 1 if summary["invalid"] else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--visual-review-sheet",
        type=Path,
        default=Path("data/roadview_visual_review_sheet.json"),
        help="Base roadview visual review sheet JSON.",
    )
    parser.add_argument("--decisions-csv", type=Path, required=True, help="Filled visual review decisions CSV.")
    parser.add_argument("--output", type=Path, required=True, help="Updated visual review sheet JSON.")
    parser.add_argument("--report-output", type=Path, required=True, help="Decision import report JSON.")
    parser.add_argument("--reviewer", default="operator", help="Default reviewer if a row leaves reviewer blank.")
    parser.add_argument("--reviewed-at", help="Default review date in YYYY-MM-DD. Defaults to generated-at.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
