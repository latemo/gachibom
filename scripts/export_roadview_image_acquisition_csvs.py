"""Export roadview image acquisition request lists as CSV files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_new_candidates import export_roadview_image_acquisition_csvs, load_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = export_roadview_image_acquisition_csvs(
        load_json(args.acquisition_request),
        priority_output=args.priority_output,
        full_output=args.full_output,
        summary_output=args.summary_output,
    )
    print(f"priority_output={args.priority_output}")
    print(f"full_output={args.full_output}")
    print(f"summary_output={args.summary_output}")
    print(
        "summary="
        f"priority:{summary['priority_rows']}, "
        f"full:{summary['full_rows']}, "
        f"places:{summary['summary_rows']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-request", type=Path, required=True, help="Roadview acquisition request JSON.")
    parser.add_argument("--priority-output", type=Path, required=True, help="Priority sample CSV output.")
    parser.add_argument("--full-output", type=Path, required=True, help="Full service-seed image CSV output.")
    parser.add_argument("--summary-output", type=Path, required=True, help="Place summary CSV output.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
