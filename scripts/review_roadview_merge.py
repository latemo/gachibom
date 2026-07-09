"""Generate a merge-review report for roadview accessibility card drafts."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.roadview_merge import build_merge_review_report, load_json, write_json


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = date.fromisoformat(args.generated_at) if args.generated_at else date.today()
    report = build_merge_review_report(
        load_json(args.existing),
        load_json(args.draft),
        generated_at=generated_at,
    )
    write_json(report, args.output)
    summary = report["summary"]
    print(f"report_output={args.output}")
    print(
        "summary="
        f"existing:{summary['existing_count']}, "
        f"draft:{summary['draft_count']}, "
        f"matched_existing:{summary['matched_existing']}, "
        f"new_candidate:{summary['new_candidate']}, "
        f"needs_manual_review:{summary['needs_manual_review']}, "
        f"field_updates_available:{summary['field_updates_available']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True, help="Existing accessibility cards JSON.")
    parser.add_argument("--draft", type=Path, required=True, help="Roadview draft accessibility cards JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output review report JSON.")
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
