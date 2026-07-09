"""Apply a filled roadview visual review sheet to the image review report."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import apply_roadview_visual_review_sheet, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    result = apply_roadview_visual_review_sheet(
        load_json(args.roadview_image_review),
        load_json(args.visual_review_sheet),
        generated_at=generated_at,
    )
    write_json(result["updated_roadview_image_review"], args.output)
    write_json(result["apply_report"], args.report_output)
    summary = result["apply_report"]["summary"]
    print(f"roadview_image_review_output={args.output}")
    print(f"visual_review_apply_report_output={args.report_output}")
    print(
        "summary="
        f"total:{summary['total']}, "
        f"applied:{summary['by_action'].get('applied', 0)}, "
        f"resolved:{summary['by_new_status'].get('resolved', 0)}, "
        f"pending:{summary['by_action'].get('skipped_pending_input', 0)}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadview-image-review", type=Path, required=True, help="Base roadview image review JSON.")
    parser.add_argument("--visual-review-sheet", type=Path, required=True, help="Filled visual review sheet JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Updated roadview image review JSON.")
    parser.add_argument("--report-output", type=Path, required=True, help="Apply report JSON.")
    parser.add_argument("--generated-at", help="Apply date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
