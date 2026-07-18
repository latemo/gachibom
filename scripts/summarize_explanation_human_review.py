from __future__ import annotations

import argparse
import csv
import hmac
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.explanation_blind_review import (  # noqa: E402
    BLIND_REVIEW_CSV_FIELDS,
    BlindReviewInputError,
    compute_review_row_fingerprint,
    compute_source_fingerprint,
)
from src.explanation_human_evaluation import (  # noqa: E402
    HumanEvaluationValidationError,
    build_explanation_human_evaluation_report,
    render_explanation_human_evaluation_markdown,
)
from src.explanation_review_workbook import (  # noqa: E402
    ExplanationReviewWorkbookError,
    read_explanation_review_workbook,
)


DEFAULT_KEY = "data/explanation_eval_blind_key.json"
DEFAULT_AUTOMATIC_RESULTS = "data/explanation_eval_results.json"
DEFAULT_OUTPUT_JSON = "data/explanation_eval_human_summary.json"
DEFAULT_OUTPUT_MD = "docs/explanation_human_quality_report.md"
DEFAULT_MASTER_REVIEW_CSV = "data/explanation_eval_blind_review.csv"
REVIEWER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
ALLOWED_REVIEW_STATUSES = {"", "pending", "complete"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate, deblind, and summarize completed explanation-quality review CSV files."
    )
    parser.add_argument(
        "--review-csv",
        action="append",
        default=None,
        help="Blind review CSV; repeat once for every reviewer submission.",
    )
    parser.add_argument(
        "--review-xlsx",
        action="append",
        default=None,
        help="Reviewer workbook as REVIEWER_ID=path.xlsx; repeat for every submission.",
    )
    parser.add_argument(
        "--master-review-csv",
        default=DEFAULT_MASTER_REVIEW_CSV,
        help="Original blind-review CSV used to verify XLSX immutable content.",
    )
    parser.add_argument("--key", default=DEFAULT_KEY, help="Private deblinding key JSON.")
    parser.add_argument(
        "--automatic-results",
        default=DEFAULT_AUTOMATIC_RESULTS,
        help="Automatic evaluation report used to verify source identity and score-trace accuracy.",
    )
    parser.add_argument("--required-cases", type=positive_int, default=30)
    parser.add_argument("--min-reviewers", type=positive_int, default=3)
    parser.add_argument("--output-json", default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", default=DEFAULT_OUTPUT_MD)
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Return exit code 1 when the quality gate is pending or failed.",
    )
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if not args.review_csv and not args.review_xlsx:
            raise HumanEvaluationValidationError(
                "at least one --review-csv or --review-xlsx submission is required"
            )
        deblind_key = _load_json_object(Path(args.key), "deblind key")
        automatic_report = _load_json_object(Path(args.automatic_results), "automatic results")
        review_rows: list[dict[str, str]] = []
        if args.review_csv:
            review_rows.extend(
                _load_review_files([Path(value) for value in args.review_csv], deblind_key)
            )
        if args.review_xlsx:
            master_rows = _load_master_review_rows(Path(args.master_review_csv))
            review_rows.extend(_load_review_workbooks(args.review_xlsx, master_rows))
        report = build_explanation_human_evaluation_report(
            review_rows,
            deblind_key,
            automatic_report,
            generated_at=_utc_now(),
            required_assignment_count=args.required_cases,
            min_reviewers_per_case=args.min_reviewers,
            fingerprint_validator=_source_fingerprint_matches,
            row_fingerprint_validator=_review_row_fingerprint_matches,
        )
        markdown = render_explanation_human_evaluation_markdown(report)
        _atomic_write(
            Path(args.output_json),
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        )
        _atomic_write(Path(args.output_md), markdown)
    except (
        OSError,
        csv.Error,
        json.JSONDecodeError,
        BlindReviewInputError,
        ExplanationReviewWorkbookError,
        HumanEvaluationValidationError,
        ValueError,
    ) as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    coverage = report["coverage"]
    gate_status = report["gate"]["status"]
    print(f"output_json={args.output_json}")
    print(f"output_md={args.output_md}")
    print(
        f"summary=reviews:{coverage['completed_review_count']} "
        f"cases:{coverage['reviewed_assignment_count']}/{coverage['assignment_count']} "
        f"status:{report['human_review_status']} gate:{gate_status}"
    )
    if args.fail_on_gate and gate_status != "passed":
        return 1
    return 0


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise HumanEvaluationValidationError(f"{label} JSON must be an object")
    return value


def _load_review_files(paths: list[Path], deblind_key: dict[str, Any]) -> list[dict[str, str]]:
    assignments = deblind_key.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise HumanEvaluationValidationError("deblind_key.assignments must be a non-empty list")
    expected_ids = {
        str(item.get("blind_id") or "").strip()
        for item in assignments
        if isinstance(item, dict) and str(item.get("blind_id") or "").strip()
    }
    if len(expected_ids) != len(assignments):
        raise HumanEvaluationValidationError("deblind key contains a missing or duplicate blind_id")

    merged: list[dict[str, str]] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = set(reader.fieldnames or [])
            missing_headers = [field for field in BLIND_REVIEW_CSV_FIELDS if field not in headers]
            if missing_headers:
                if "before_answer" in headers or "after_answer" in headers:
                    raise HumanEvaluationValidationError(
                        f"{path} is a legacy unblinded review CSV and cannot be merged"
                    )
                raise HumanEvaluationValidationError(
                    f"{path} is missing blind review columns: {', '.join(missing_headers)}"
                )
            rows = [dict(row) for row in reader]

        ids = [str(row.get("blind_id") or "").strip() for row in rows]
        if len(ids) != len(expected_ids) or set(ids) != expected_ids or len(set(ids)) != len(ids):
            raise HumanEvaluationValidationError(
                f"{path} must contain each of the {len(expected_ids)} blind_id values exactly once"
            )

        reviewer_ids: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            status = str(row.get("review_status") or "").strip().casefold()
            if status not in ALLOWED_REVIEW_STATUSES:
                raise HumanEvaluationValidationError(
                    f"{path}:{row_number} review_status must be pending or complete"
                )
            row["review_status"] = status
            reviewer_id = str(row.get("reviewer_id") or "").strip()
            if reviewer_id:
                if not REVIEWER_ID_PATTERN.fullmatch(reviewer_id):
                    raise HumanEvaluationValidationError(
                        f"{path}:{row_number} reviewer_id must use 1-64 ASCII letters, digits, '_' or '-'"
                    )
                reviewer_ids.add(reviewer_id.casefold())
            if status == "complete" and not reviewer_id:
                raise HumanEvaluationValidationError(
                    f"{path}:{row_number} completed row requires reviewer_id"
                )
        if len(reviewer_ids) > 1:
            raise HumanEvaluationValidationError(f"{path} must contain exactly one reviewer_id")
        merged.extend(rows)
    return merged


def _load_master_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != tuple(BLIND_REVIEW_CSV_FIELDS):
            raise HumanEvaluationValidationError(
                "master review CSV headers must exactly match the blind-review schema"
            )
        rows = [dict(row) for row in reader]
    if not rows:
        raise HumanEvaluationValidationError("master review CSV must not be empty")
    return rows


def _load_review_workbooks(
    specifications: list[str], master_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_reviewers: set[str] = set()
    for specification in specifications:
        reviewer_id, separator, raw_path = str(specification or "").partition("=")
        reviewer_id = reviewer_id.strip()
        raw_path = raw_path.strip()
        if not separator or not reviewer_id or not raw_path:
            raise HumanEvaluationValidationError(
                "--review-xlsx must use REVIEWER_ID=path.xlsx"
            )
        if not REVIEWER_ID_PATTERN.fullmatch(reviewer_id):
            raise HumanEvaluationValidationError(
                "XLSX reviewer ID must use 1-64 ASCII letters, digits, '_' or '-'"
            )
        key = reviewer_id.casefold()
        if key in seen_reviewers:
            raise HumanEvaluationValidationError(f"duplicate XLSX reviewer ID: {reviewer_id}")
        seen_reviewers.add(key)
        merged.extend(
            read_explanation_review_workbook(
                Path(raw_path),
                master_rows,
                expected_reviewer_id=reviewer_id,
            )
        )
    return merged


def _source_fingerprint_matches(key: dict[str, Any], report: dict[str, Any]) -> bool:
    expected = str(key.get("source_fingerprint") or "")
    actual = compute_source_fingerprint(report)
    return bool(expected) and hmac.compare_digest(expected, actual)


def _review_row_fingerprint_matches(row: dict[str, Any], assignment: dict[str, str]) -> bool:
    expected = str(assignment.get("immutable_fingerprint") or "")
    actual = compute_review_row_fingerprint(row)
    return bool(expected) and hmac.compare_digest(expected, actual)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
