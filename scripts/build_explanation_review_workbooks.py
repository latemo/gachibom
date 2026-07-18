from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.explanation_blind_review import BLIND_REVIEW_CSV_FIELDS  # noqa: E402
from src.explanation_review_workbook import (  # noqa: E402
    ExplanationReviewWorkbookError,
    write_explanation_review_workbook,
)


DEFAULT_MASTER_CSV = "data/explanation_eval_blind_review.csv"
DEFAULT_OUTPUT_DIR = "outputs/explanation-review-20260712"
DEFAULT_REVIEWERS = ("R01", "R02", "R03")
REVIEWER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reviewer-friendly blind-review XLSX files.")
    parser.add_argument("--master-csv", default=DEFAULT_MASTER_CSV)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--reviewer",
        action="append",
        default=None,
        help="Pseudonymous reviewer ID; repeat for multiple files (default: R01, R02, R03).",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing reviewer workbooks.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    reviewers = args.reviewer or list(DEFAULT_REVIEWERS)
    output_dir = Path(args.output_dir)
    try:
        normalized_reviewers = _validate_reviewers(reviewers)
        master_rows = _load_master_rows(Path(args.master_csv))
        targets = [output_dir / f"gachibom_explanation_review_{reviewer}.xlsx" for reviewer in normalized_reviewers]
        if not args.force:
            existing = [str(path) for path in targets if path.exists()]
            if existing:
                raise ExplanationReviewWorkbookError(
                    "refusing to replace existing reviewer workbook(s); use --force before distribution: "
                    + ", ".join(existing)
                )

        output_dir.mkdir(parents=True, exist_ok=True)
        for reviewer, target in zip(normalized_reviewers, targets):
            temporary = target.with_name(f".{target.stem}.tmp.xlsx")
            try:
                write_explanation_review_workbook(temporary, master_rows, reviewer_id=reviewer)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
    except (OSError, csv.Error, ExplanationReviewWorkbookError, ValueError) as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    for path in targets:
        print(f"workbook={path}")
    print(f"summary=reviewers:{len(targets)} cases_per_workbook:{len(master_rows)}")
    return 0


def _validate_reviewers(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        reviewer = str(value or "").strip()
        if not REVIEWER_ID_PATTERN.fullmatch(reviewer):
            raise ExplanationReviewWorkbookError(
                "reviewer IDs must use 1-64 ASCII letters, digits, '_' or '-'"
            )
        key = reviewer.casefold()
        if key in seen:
            raise ExplanationReviewWorkbookError(f"duplicate reviewer ID: {reviewer}")
        seen.add(key)
        result.append(reviewer)
    if not result:
        raise ExplanationReviewWorkbookError("at least one reviewer ID is required")
    return result


def _load_master_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != tuple(BLIND_REVIEW_CSV_FIELDS):
            raise ExplanationReviewWorkbookError(
                "master CSV headers must exactly match the blind-review schema"
            )
        rows = [dict(row) for row in reader]
    blind_ids = [str(row.get("blind_id") or "").strip() for row in rows]
    if not rows or any(not value for value in blind_ids) or len(set(blind_ids)) != len(blind_ids):
        raise ExplanationReviewWorkbookError("master CSV must contain unique non-empty blind_id values")
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
