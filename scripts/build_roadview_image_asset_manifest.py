"""Build a local asset manifest for roadview image visual review."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import build_roadview_image_asset_manifest, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    manifest = build_roadview_image_asset_manifest(
        load_json(args.roadview_image_review),
        asset_root=args.asset_root,
        generated_at=generated_at,
    )
    write_json(manifest, args.output)
    summary = manifest["summary"]
    print(f"roadview_image_asset_manifest_output={args.output}")
    print(
        "summary="
        f"places:{summary['total_places']}, "
        f"samples:{summary['expected_review_sample_images']}, "
        f"available:{summary['available_review_sample_images']}, "
        f"missing:{summary['missing_review_sample_images']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadview-image-review", type=Path, required=True, help="Roadview image review JSON.")
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=Path("data/raw/roadview_images"),
        help="Directory where roadview image files are stored.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output roadview image asset manifest JSON.")
    parser.add_argument("--generated-at", help="Manifest date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
