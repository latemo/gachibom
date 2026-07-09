"""Apply reviewed roadview conflict resolutions to cards and open review queue."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_merge import apply_manual_conflict_resolutions, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    applied_at = date.fromisoformat(args.applied_at) if args.applied_at else date.today()
    result = apply_manual_conflict_resolutions(
        load_json(args.existing),
        load_json(args.manual_review),
        load_json(args.resolutions),
        applied_at=applied_at,
    )
    write_json(result["cards"], args.output)
    write_json(result["open_manual_review_queue"], args.open_manual_review_output)
    write_json(result["resolution_apply_report"], args.apply_report_output)

    summary = result["resolution_apply_report"]["summary"]
    print(f"cards_output={args.output}")
    print(f"open_manual_review_output={args.open_manual_review_output}")
    print(f"apply_report_output={args.apply_report_output}")
    print(
        "summary="
        f"resolutions_applied:{summary['resolutions_applied']}, "
        f"resolutions_skipped:{summary['resolutions_skipped']}, "
        f"manual_review_items_after:{summary['manual_review_items_after']}, "
        f"resolved_field_conflict_items:{summary['resolved_field_conflict_items']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True, help="Existing accessibility cards JSON.")
    parser.add_argument("--manual-review", type=Path, required=True, help="Current manual review queue JSON.")
    parser.add_argument("--resolutions", type=Path, required=True, help="Reviewed conflict resolutions JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output accessibility cards JSON.")
    parser.add_argument("--open-manual-review-output", type=Path, required=True, help="Remaining open review queue JSON.")
    parser.add_argument("--apply-report-output", type=Path, required=True, help="Resolution apply report JSON.")
    parser.add_argument("--applied-at", help="Apply date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
