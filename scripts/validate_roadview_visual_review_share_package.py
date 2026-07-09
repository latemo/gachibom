"""Validate the portable roadview visual review share package."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_image_download import write_json
from src.roadview_review_exports import validate_visual_review_share_package


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = validate_visual_review_share_package(
        package_dir=args.package_dir,
        zip_path=args.zip_path,
        expected_assets=args.expected_assets,
        expected_contact_sheets=args.expected_contact_sheets,
        expected_place_csvs=args.expected_place_csvs,
        generated_at=generated_at,
    )
    write_json(report, args.output)
    summary = report["summary"]
    print(f"visual_review_share_validation_report={args.output}")
    print(
        "summary="
        f"status:{report['status']}, "
        f"checks:{summary['total_checks']}, "
        f"pass:{summary['passed_checks']}, "
        f"fail:{summary['failed_checks']}, "
        f"zip_sha256:{summary['zip_sha256']}"
    )
    return 0 if report["status"] == "pass" else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=Path("docs/roadview_visual_review_share"),
        help="Portable share package directory.",
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        default=Path("docs/roadview_visual_review_share.zip"),
        help="Portable share package ZIP.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/roadview_visual_review_share_validation_report.json"),
        help="Output validation report JSON.",
    )
    parser.add_argument("--expected-assets", type=int, default=102)
    parser.add_argument("--expected-contact-sheets", type=int, default=17)
    parser.add_argument("--expected-place-csvs", type=int, default=17)
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
