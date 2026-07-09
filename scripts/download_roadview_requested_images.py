"""Download requested roadview image files from the public Jeju GIS endpoint."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_image_download import build_roadview_image_download_report, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_roadview_image_download_report(
        load_json(args.acquisition_request),
        target_root=args.target_root,
        tier=args.tier,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout_seconds,
        limit=args.limit,
        generated_at=generated_at,
    )
    write_json(report, args.output)
    summary = report["summary"]
    print(f"roadview_image_download_report_output={args.output}")
    print(
        "summary="
        f"tier:{report['tier']}, "
        f"items:{summary['total_items']}, "
        f"downloaded:{summary['downloaded']}, "
        f"skipped:{summary['skipped_existing']}, "
        f"planned:{summary['planned']}, "
        f"failed:{summary['failed']}, "
        f"bytes:{summary['bytes_downloaded']}"
    )
    return 1 if summary["failed"] else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acquisition-request",
        type=Path,
        default=Path("data/roadview_image_acquisition_request.json"),
        help="Roadview image acquisition request JSON.",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path("data/raw/roadview_images"),
        help="Directory where image files are written.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output download report JSON.")
    parser.add_argument("--tier", choices=["priority", "supplemental", "all"], default="priority")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--limit", type=int, help="Download at most this many images.")
    parser.add_argument("--overwrite", action="store_true", help="Re-download existing files.")
    parser.add_argument("--dry-run", action="store_true", help="Build a plan without downloading files.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
