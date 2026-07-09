"""Apply conservative roadview accessibility updates and write review artifacts."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_merge import apply_safe_roadview_updates, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    applied_at = date.fromisoformat(args.applied_at) if args.applied_at else date.today()
    result = apply_safe_roadview_updates(
        load_json(args.existing),
        load_json(args.report),
        applied_at=applied_at,
    )
    write_json(result["cards"], args.output)
    write_json(result["manual_review_queue"], args.manual_review_output)
    write_json(result["apply_report"], args.apply_report_output)

    summary = result["apply_report"]["summary"]
    review_summary = result["manual_review_queue"]["summary"]
    print(f"cards_output={args.output}")
    print(f"manual_review_output={args.manual_review_output}")
    print(f"apply_report_output={args.apply_report_output}")
    print(
        "summary="
        f"cards_updated:{summary['cards_updated']}, "
        f"safe_field_updates_applied:{summary['safe_field_updates_applied']}, "
        f"skipped_field_updates:{summary['skipped_field_updates']}, "
        f"manual_review_items:{review_summary['total']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True, help="Existing accessibility cards JSON.")
    parser.add_argument("--report", type=Path, required=True, help="Roadview merge review report JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Merged accessibility cards JSON.")
    parser.add_argument("--manual-review-output", type=Path, required=True, help="Manual review queue JSON.")
    parser.add_argument("--apply-report-output", type=Path, required=True, help="Safe update apply report JSON.")
    parser.add_argument("--applied-at", help="Apply date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
