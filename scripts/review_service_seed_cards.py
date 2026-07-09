"""Build a pre-publish review report for roadview service seed cards."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_service_seed_review, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_service_seed_review(
        load_json(args.seed_cards),
        load_json(args.image_metadata),
        generated_at=generated_at,
    )
    write_json(report, args.output)
    summary = report["summary"]
    print(f"review_output={args.output}")
    print(
        "summary="
        f"total:{summary['total']}, "
        f"blocked:{summary['by_decision'].get('blocked_pending_detail_review', 0)}, "
        f"publishable:{summary['by_decision'].get('publishable_after_final_review', 0)}, "
        f"total_roadview_images:{summary['total_roadview_images']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-cards", type=Path, required=True, help="Roadview service seed candidate cards JSON.")
    parser.add_argument("--image-metadata", type=Path, required=True, help="Roadview image metadata JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output service seed review report JSON.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
