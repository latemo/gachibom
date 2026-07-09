"""Build a focused acquisition request for roadview image source files."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_roadview_image_acquisition_request, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    request = build_roadview_image_acquisition_request(
        load_json(args.roadview_image_review),
        load_json(args.image_metadata),
        generated_at=generated_at,
    )
    write_json(request, args.output)
    summary = request["summary"]
    print(f"roadview_image_acquisition_request_output={args.output}")
    print(
        "summary="
        f"places:{summary['total_places']}, "
        f"priority:{summary['priority_sample_images']}, "
        f"supplemental:{summary['supplemental_images']}, "
        f"total:{summary['total_requested_images']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadview-image-review", type=Path, required=True, help="Roadview image review JSON.")
    parser.add_argument("--image-metadata", type=Path, required=True, help="Roadview image metadata JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output acquisition request JSON.")
    parser.add_argument("--generated-at", help="Request date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
