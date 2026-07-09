"""Build a report for roadview image metadata entries whose source image returns 404."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_image_download import build_roadview_provider_404_image_report, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_roadview_provider_404_image_report(
        load_json(args.download_report),
        generated_at=generated_at,
    )
    write_json(report, args.output)
    summary = report["summary"]
    print(f"roadview_provider_404_image_report_output={args.output}")
    print(
        "summary="
        f"provider_404:{summary['provider_404_images']}, "
        f"affected_places:{summary['affected_places']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download-report",
        type=Path,
        default=Path("data/roadview_image_download_report.all.json"),
        help="Roadview image download report JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output provider 404 image report JSON.",
    )
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
