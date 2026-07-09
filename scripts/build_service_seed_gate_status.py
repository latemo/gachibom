"""Build a consolidated gate status report for roadview service seed promotion."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_service_seed_gate_status, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_service_seed_gate_status(
        load_json(args.acquisition_request),
        load_json(args.receipt_report),
        load_json(args.image_asset_manifest),
        load_json(args.visual_review_sheet),
        load_json(args.promotion_readiness),
        load_json(args.active_candidate_report),
        generated_at=generated_at,
    )
    write_json(report, args.output)
    summary = report["summary"]
    print(f"service_seed_gate_status_output={args.output}")
    print(
        "summary="
        f"status:{report['overall_status']}, "
        f"stage:{report['current_primary_stage']}, "
        f"places:{summary['total_places']}, "
        f"ready:{summary['ready_for_service_activation_count']}, "
        f"blocked:{summary['blocked_count']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-request", type=Path, required=True, help="Roadview image acquisition request JSON.")
    parser.add_argument("--receipt-report", type=Path, required=True, help="Roadview image receipt report JSON.")
    parser.add_argument("--image-asset-manifest", type=Path, required=True, help="Roadview image asset manifest JSON.")
    parser.add_argument("--visual-review-sheet", type=Path, required=True, help="Roadview visual review sheet JSON.")
    parser.add_argument("--promotion-readiness", type=Path, required=True, help="Service seed promotion readiness JSON.")
    parser.add_argument("--active-candidate-report", type=Path, required=True, help="Service seed active candidate report JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output consolidated gate status JSON.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
