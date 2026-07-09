"""Build place-level contact sheets and CSV files for roadview visual review."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_image_download import write_json
from src.roadview_review_exports import build_visual_review_packets, load_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_visual_review_packets(
        load_json(args.visual_review_sheet),
        contact_sheet_dir=args.contact_sheet_dir,
        csv_dir=args.csv_dir,
        index_output=args.index_output,
        generated_at=generated_at,
    )
    write_json(report, args.report_output)
    print(f"visual_review_packet_index_output={args.index_output}")
    print(f"visual_review_packet_report_output={args.report_output}")
    print(
        "summary="
        f"places:{report['total_places']}, "
        f"contact_sheets:{report['contact_sheet_count']}, "
        f"csv_files:{report['decision_csv_count']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--visual-review-sheet",
        type=Path,
        default=Path("data/roadview_visual_review_sheet.json"),
        help="Roadview visual review sheet JSON.",
    )
    parser.add_argument(
        "--contact-sheet-dir",
        type=Path,
        default=Path("docs/roadview_visual_review_packets/contact_sheets"),
        help="Output directory for place contact sheet JPEG files.",
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("data/roadview_visual_review_decisions_by_place"),
        help="Output directory for place-level CSV files.",
    )
    parser.add_argument(
        "--index-output",
        type=Path,
        default=Path("docs/roadview_visual_review_packets/index.html"),
        help="Output HTML index.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("data/roadview_visual_review_packet_report.json"),
        help="Output packet build report JSON.",
    )
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
