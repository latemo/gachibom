"""Build the service operations readiness report."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.operations_readiness import build_operations_readiness_report, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_operations_readiness_report(
        load_json(args.place_cards),
        load_json(args.data_request_tracker),
        load_json(args.service_seed_gate_status),
        generated_at=generated_at,
        workspace_root=ROOT,
    )
    write_json(report, args.output)
    if args.web_output:
        write_json(report, args.web_output)
    summary = report["summary"]
    print(f"operations_readiness_report_output={args.output}")
    if args.web_output:
        print(f"operations_readiness_report_web_output={args.web_output}")
    print(
        "summary="
        f"status:{report['overall_status']}, "
        f"checks:{summary['total_checks']}, "
        f"pass:{summary['passed_checks']}, "
        f"warn:{summary['warning_checks']}, "
        f"block:{summary['blocker_checks']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--place-cards",
        type=Path,
        default=Path("data/jeju_accessible_spots.json"),
        help="Primary accessibility place cards JSON.",
    )
    parser.add_argument(
        "--data-request-tracker",
        type=Path,
        default=Path("data/data_request_tracker.json"),
        help="Data request tracker JSON.",
    )
    parser.add_argument(
        "--service-seed-gate-status",
        type=Path,
        default=Path("data/roadview_service_seed_gate_status.json"),
        help="Consolidated service seed gate status JSON.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output operations readiness report JSON.")
    parser.add_argument("--web-output", type=Path, help="Optional app-facing copy under web/data.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
