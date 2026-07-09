"""Build operational work items from the roadview service seed review report."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_service_seed_work_queue, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    queue = build_service_seed_work_queue(load_json(args.review), generated_at=generated_at)
    write_json(queue, args.output)
    summary = queue["summary"]
    print(f"work_queue_output={args.output}")
    print(
        "summary="
        f"total:{summary['total']}, "
        f"high:{summary['by_priority'].get('high', 0)}, "
        f"medium:{summary['by_priority'].get('medium', 0)}, "
        f"open:{summary['by_status'].get('open', 0)}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True, help="Roadview service seed review report JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output operational work queue JSON.")
    parser.add_argument("--generated-at", help="Queue date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
