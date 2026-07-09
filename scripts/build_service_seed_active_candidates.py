"""Build active candidate cards from promotion-ready roadview service seed cards."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_service_seed_active_candidates, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    result = build_service_seed_active_candidates(
        load_json(args.seed_cards),
        load_json(args.promotion_readiness),
        load_json(args.official_source_review),
        load_json(args.category_refinement_review) if args.category_refinement_review else None,
        generated_at=generated_at,
    )
    write_json(result["active_candidates"], args.output)
    write_json(result["promotion_report"], args.report_output)
    summary = result["promotion_report"]["summary"]
    print(f"active_candidates_output={args.output}")
    print(f"active_candidate_report_output={args.report_output}")
    print(
        "summary="
        f"total:{summary['total']}, "
        f"promoted:{summary['promoted_count']}, "
        f"blocked:{summary['blocked_count']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-cards", type=Path, required=True, help="Roadview service seed card JSON.")
    parser.add_argument("--promotion-readiness", type=Path, required=True, help="Promotion readiness JSON.")
    parser.add_argument("--official-source-review", type=Path, required=True, help="Official source review JSON.")
    parser.add_argument("--category-refinement-review", type=Path, help="Optional category refinement review JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output active candidate card JSON.")
    parser.add_argument("--report-output", type=Path, required=True, help="Output active candidate report JSON.")
    parser.add_argument("--generated-at", help="Candidate generation date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
