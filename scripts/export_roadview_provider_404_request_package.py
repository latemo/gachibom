"""Export provider-facing CSV and request message for roadview image 404 recovery."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_review_exports import (
    build_provider_404_recovery_request_markdown,
    export_provider_404_image_request_csv,
    load_json,
    write_text,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = load_json(args.provider_404_report)
    csv_summary = export_provider_404_image_request_csv(report, args.csv_output)
    write_text(
        build_provider_404_recovery_request_markdown(report, generated_at=generated_at),
        args.message_output,
    )
    summary = report.get("summary", {})
    print(f"provider_404_csv_output={args.csv_output}")
    print(f"provider_404_message_output={args.message_output}")
    print(
        "summary="
        f"rows:{csv_summary['rows']}, "
        f"provider_404:{summary.get('provider_404_images', 0)}, "
        f"affected_places:{summary.get('affected_places', 0)}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-404-report",
        type=Path,
        default=Path("data/roadview_provider_404_image_report.json"),
        help="Provider 404 image report JSON.",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        required=True,
        help="Output CSV for provider recovery request.",
    )
    parser.add_argument(
        "--message-output",
        type=Path,
        required=True,
        help="Output Markdown request message.",
    )
    parser.add_argument("--generated-at", help="Request date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
