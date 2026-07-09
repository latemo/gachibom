"""Triage roadview new candidates before service-card promotion."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import (
    build_service_seed_cards,
    load_json,
    triage_new_candidates,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    queue = load_json(args.queue)
    drafts = load_json(args.draft)
    report = triage_new_candidates(queue, drafts, generated_at=generated_at)
    write_json(report, args.output)

    if args.seed_output:
        seed_cards = build_service_seed_cards(report, drafts, seed_status=args.seed_status)
        write_json(seed_cards, args.seed_output)
        print(f"seed_output={args.seed_output}")
        print(f"service_seed_cards={len(seed_cards)}")

    summary = report["summary"]
    decisions = summary["by_decision"]
    print(f"triage_output={args.output}")
    print(
        "summary="
        f"total:{summary['total']}, "
        f"service_seed_candidate:{decisions.get('service_seed_candidate', 0)}, "
        f"catalog_candidate:{decisions.get('catalog_candidate', 0)}, "
        f"field_review_required:{decisions.get('field_review_required', 0)}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True, help="Current manual review queue JSON.")
    parser.add_argument("--draft", type=Path, required=True, help="Roadview draft accessibility cards JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output new-candidate triage JSON.")
    parser.add_argument("--seed-output", type=Path, help="Optional service seed candidate cards JSON.")
    parser.add_argument("--seed-status", default="hidden", choices=["active", "hidden"], help="Status for seed cards.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
