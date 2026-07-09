"""Import Jeju social-vulnerable roadview image metadata CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_data import IMAGE_METADATA_SOURCE_URL, load_csv_rows, metadata_rows_to_records, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = load_csv_rows(args.input, encoding=args.encoding)
    records = metadata_rows_to_records(rows, source_url=args.source_url)
    write_json(records, args.output)
    print(f"metadata_output={args.output}")
    print(f"metadata_imported={len(records)}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="15109158 image metadata CSV path.")
    parser.add_argument("--output", type=Path, required=True, help="Output roadview metadata JSON.")
    parser.add_argument("--source-url", default=IMAGE_METADATA_SOURCE_URL, help="Source dataset URL.")
    parser.add_argument("--encoding", default="utf-8-sig", help="CSV encoding.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
