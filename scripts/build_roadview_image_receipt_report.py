"""Build a receipt quality report for delivered roadview image files."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_roadview_image_receipt_report, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_roadview_image_receipt_report(
        load_json(args.acquisition_request),
        receipt_root=args.receipt_root,
        generated_at=generated_at,
        hash_files=not args.skip_hash,
    )
    write_json(report, args.output)
    summary = report["summary"]
    print(f"roadview_image_receipt_report_output={args.output}")
    print(
        "summary="
        f"places:{summary['total_places']}, "
        f"expected:{summary['expected_images']}, "
        f"received:{summary['received_requested_images']}, "
        f"missing:{summary['missing_requested_images']}, "
        f"unexpected:{summary['unexpected_file_count']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-request", type=Path, required=True, help="Roadview image acquisition request JSON.")
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path("data/raw/roadview_images"),
        help="Directory containing delivered roadview image files.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output receipt report JSON.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--skip-hash", action="store_true", help="Skip SHA-256 hashing for large delivered datasets.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
