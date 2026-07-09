"""Build official-source review items from the roadview service seed work queue."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_official_source_review, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    review = build_official_source_review(load_json(args.work_queue), generated_at=generated_at)
    write_json(review, args.output)
    summary = review["summary"]
    print(f"official_source_review_output={args.output}")
    print(
        "summary="
        f"total:{summary['total']}, "
        f"open:{summary['by_status'].get('open', 0)}, "
        f"pending:{summary['by_review_decision'].get('pending_source_verification', 0)}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-queue", type=Path, required=True, help="Roadview service seed work queue JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output official source review JSON.")
    parser.add_argument("--generated-at", help="Review date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
