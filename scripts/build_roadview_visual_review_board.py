"""Build an HTML board for operator roadview visual review."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_review_exports import build_roadview_visual_review_board_html, load_json, write_text


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    sheet = load_json(args.visual_review_sheet)
    provider_404_report = load_json(args.provider_404_report) if args.provider_404_report else None
    html = build_roadview_visual_review_board_html(
        sheet,
        provider_404_report=provider_404_report,
        output_path=args.output,
        generated_at=generated_at,
    )
    write_text(html, args.output)
    summary = sheet.get("summary", {})
    print(f"roadview_visual_review_board_output={args.output}")
    print(
        "summary="
        f"places:{summary.get('total_places', 0)}, "
        f"fields:{summary.get('total_field_results', 0)}, "
        f"pending:{summary.get('by_field_status', {}).get('pending_visual_review', 0)}"
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
        "--provider-404-report",
        type=Path,
        default=Path("data/roadview_provider_404_image_report.json"),
        help="Optional provider 404 report JSON.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output HTML review board.")
    parser.add_argument("--generated-at", help="Board date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
