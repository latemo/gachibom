"""Build a manual visual review sheet for roadview image verification."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_roadview_visual_review_sheet, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    sheet = build_roadview_visual_review_sheet(
        load_json(args.roadview_image_review),
        load_json(args.image_asset_manifest),
        generated_at=generated_at,
    )
    write_json(sheet, args.output)
    summary = sheet["summary"]
    print(f"roadview_visual_review_sheet_output={args.output}")
    print(
        "summary="
        f"places:{summary['total_places']}, "
        f"blocked:{summary['by_status'].get('blocked', 0)}, "
        f"open:{summary['by_status'].get('open', 0)}, "
        f"fields:{summary['total_field_results']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadview-image-review", type=Path, required=True, help="Roadview image review JSON.")
    parser.add_argument("--image-asset-manifest", type=Path, required=True, help="Roadview image asset manifest JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output manual visual review sheet JSON.")
    parser.add_argument("--generated-at", help="Sheet date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
