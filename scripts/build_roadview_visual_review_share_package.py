"""Build a portable share package for roadview visual review."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_image_download import write_json
from src.roadview_review_exports import build_shareable_visual_review_package, load_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_shareable_visual_review_package(
        load_json(args.visual_review_sheet),
        package_dir=args.package_dir,
        provider_404_report=load_json(args.provider_404_report) if args.provider_404_report else None,
        generated_at=generated_at,
        max_image_width=args.max_image_width,
    )
    zip_output = make_zip(args.package_dir, args.zip_output)
    report["zip_output"] = str(args.zip_output).replace("\\", "/")
    write_json(report, args.report_output)
    print(f"visual_review_share_package_dir={args.package_dir}")
    print(f"visual_review_share_package_zip={zip_output}")
    print(f"visual_review_share_package_report={args.report_output}")
    print(
        "summary="
        f"places:{report['total_places']}, "
        f"images:{report['copied_image_count']}, "
        f"zip:{zip_output}"
    )
    return 0


def make_zip(package_dir: Path, zip_output: Path) -> Path:
    zip_output.parent.mkdir(parents=True, exist_ok=True)
    archive_base = zip_output.with_suffix("")
    result = shutil.make_archive(str(archive_base), "zip", root_dir=package_dir)
    return Path(result)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--visual-review-sheet",
        type=Path,
        default=Path("data/roadview_visual_review_sheet.json"),
        help="Roadview visual review sheet JSON.",
    )
    parser.add_argument(
        "--provider-404-report",
        type=Path,
        default=Path("data/roadview_provider_404_image_report.json"),
        help="Optional provider 404 report JSON.",
    )
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=Path("docs/roadview_visual_review_share"),
        help="Output portable package directory.",
    )
    parser.add_argument(
        "--zip-output",
        type=Path,
        default=Path("docs/roadview_visual_review_share.zip"),
        help="Output ZIP file.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("data/roadview_visual_review_share_package_report.json"),
        help="Output package report JSON.",
    )
    parser.add_argument("--max-image-width", type=int, default=1600)
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
