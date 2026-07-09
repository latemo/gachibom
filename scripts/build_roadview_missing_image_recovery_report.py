"""Build a recovery verification report for roadview provider-404 image files."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_missing_image_recovery import (
    build_roadview_missing_image_recovery_report,
    load_json,
    render_roadview_missing_image_recovery_markdown,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_roadview_missing_image_recovery_report(
        load_json(args.provider_404_report),
        receipt_root=args.receipt_root,
        generated_at=generated_at,
        hash_files=not args.skip_hash,
    )
    write_json(report, args.output)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_roadview_missing_image_recovery_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(f"roadview_missing_image_recovery_report_output={args.output}")
    if args.output_md:
        print(f"roadview_missing_image_recovery_report_md={args.output_md}")
    print(
        "summary="
        f"status:{report['overall_status']}, "
        f"expected:{summary['expected_recovery_images']}, "
        f"recovered:{summary['recovered_images']}, "
        f"missing:{summary['still_missing_images']}, "
        f"duplicates:{summary['duplicate_name_images']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-404-report",
        type=Path,
        default=Path("data/roadview_provider_404_image_report.json"),
        help="Provider 404 missing image report JSON.",
    )
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path("data/raw/roadview_images"),
        help="Directory containing delivered roadview image files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/roadview_missing_image_recovery_report.json"),
        help="Output recovery verification report JSON.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("docs/roadview_missing_image_recovery_report_20260709.md"),
        help="Optional Markdown report for operators.",
    )
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--skip-hash", action="store_true", help="Skip SHA-256 hashing for recovered files.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
