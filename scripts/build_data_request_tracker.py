"""Build a public data request and receipt tracking ledger."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_request_tracker import (
    build_data_request_tracker,
    export_data_request_tracker_csv,
    load_json,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    tracker = build_data_request_tracker(
        acquisition_request=load_optional_json(args.acquisition_request),
        receipt_report=load_optional_json(args.receipt_report),
        service_seed_gate_status=load_optional_json(args.service_seed_gate_status),
        generated_at=generated_at,
        workspace_root=ROOT,
    )
    write_json(tracker, args.output)
    csv_summary = export_data_request_tracker_csv(tracker, args.csv_output)
    summary = tracker["summary"]
    print(f"data_request_tracker_output={args.output}")
    print(f"data_request_tracker_csv_output={args.csv_output}")
    print(
        "summary="
        f"sources:{summary['total_sources']}, "
        f"ready:{summary['ready_to_use_sources']}, "
        f"action_required:{summary['action_required_sources']}, "
        f"csv_rows:{csv_summary['rows']}"
    )
    return 0


def load_optional_json(path: Path | None) -> dict:
    if path and path.exists():
        return load_json(path)
    return {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acquisition-request",
        type=Path,
        default=Path("data/roadview_image_acquisition_request.json"),
        help="Roadview image acquisition request JSON.",
    )
    parser.add_argument(
        "--receipt-report",
        type=Path,
        default=Path("data/roadview_image_receipt_report.json"),
        help="Roadview image receipt report JSON.",
    )
    parser.add_argument(
        "--service-seed-gate-status",
        type=Path,
        default=Path("data/roadview_service_seed_gate_status.json"),
        help="Consolidated service seed gate status JSON.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output data request tracker JSON.")
    parser.add_argument("--csv-output", type=Path, required=True, help="Output data request tracker CSV.")
    parser.add_argument("--generated-at", help="Tracker date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
