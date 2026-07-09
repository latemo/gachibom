"""Build crowd policy review items from the roadview service seed work queue."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_crowd_policy_review, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    review = build_crowd_policy_review(load_json(args.work_queue), generated_at=generated_at)
    write_json(review, args.output)
    summary = review["summary"]
    print(f"crowd_policy_review_output={args.output}")
    print(
        "summary="
        f"total:{summary['total']}, "
        f"resolved:{summary['by_status'].get('resolved', 0)}, "
        f"calendar_check_required:{summary['operating_calendar_check_required']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-queue", type=Path, required=True, help="Roadview service seed work queue JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output crowd policy review JSON.")
    parser.add_argument("--generated-at", help="Review date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
