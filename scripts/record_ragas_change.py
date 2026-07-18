from __future__ import annotations

import argparse
import hashlib
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

from src.ragas_change_tracking import (  # noqa: E402
    RagasChangeTrackingError,
    append_history_change,
    build_change_detail_report,
    build_initial_history,
    build_run_snapshot,
    compare_runs,
    parse_dataset_jsonl,
    render_change_detail_markdown,
    render_history_markdown,
)


RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,79}$")
DEFAULT_TRACKED_FILES = (
    "src/help_chatbot_service.py",
    "scripts/run_explanation_ab_eval.py",
    "src/ragas_faithfulness_evaluation.py",
    "scripts/run_ragas_faithfulness_eval.py",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record an immutable RAGAS baseline or before/after change."
    )
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument(
        "--tracked-file", action="append", default=list(DEFAULT_TRACKED_FILES)
    )
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--allow-evidence-change", action="store_true")
    parser.add_argument("--previous-run", default=None)
    parser.add_argument("--dataset", default="data/ragas_faithfulness_dataset.jsonl")
    parser.add_argument("--manifest", default="data/ragas_faithfulness_manifest.json")
    parser.add_argument("--scores", default="data/ragas_faithfulness_scores.json")
    parser.add_argument("--report", default="data/ragas_faithfulness_report.json")
    parser.add_argument("--cases", default="data/explanation_eval_cases.json")
    parser.add_argument("--results", default="data/explanation_eval_results.json")
    parser.add_argument("--run-root", default="data/ragas_metric_runs")
    parser.add_argument("--history-output", default="data/ragas_change_history.json")
    parser.add_argument("--markdown-output", default="docs/ragas_change_history.md")
    parser.add_argument("--change-report-root", default="data/ragas_change_reports")
    parser.add_argument("--change-report-doc-root", default="docs/ragas_change_reports")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not RUN_ID_PATTERN.fullmatch(args.change_id):
        print(
            "error=change-id must be 3-80 lowercase letters, digits, hyphens, or underscores",
            file=sys.stderr,
        )
        return 2
    if not args.reason.strip():
        print("error=reason must not be empty", file=sys.stderr)
        return 2

    dataset_path = _path(args.dataset)
    manifest_path = _path(args.manifest)
    scores_path = _path(args.scores)
    report_path = _path(args.report)
    cases_path = _path(args.cases)
    results_path = _path(args.results)
    history_path = _path(args.history_output)
    markdown_path = _path(args.markdown_output)
    run_path = _path(args.run_root) / f"{args.change_id}.json"

    if run_path.exists():
        print(f"error=immutable run already exists: {_display_path(run_path)}", file=sys.stderr)
        return 2
    if args.baseline and history_path.exists():
        print(
            f"error=history already exists; baseline cannot be replaced: {_display_path(history_path)}",
            file=sys.stderr,
        )
        return 2

    try:
        dataset_rows = parse_dataset_jsonl(
            dataset_path.read_text(encoding="utf-8-sig")
        )
        manifest = _load_json_object(manifest_path)
        scores = _load_json_object(scores_path)
        report = _load_json_object(report_path)
        fingerprint_paths = {
            path
            for path in (
                cases_path,
                results_path,
                dataset_path,
                manifest_path,
                scores_path,
                report_path,
                *(_path(value) for value in args.tracked_file),
                *(_path(value) for value in args.changed_file),
            )
        }
        snapshot = build_run_snapshot(
            run_id=args.change_id,
            recorded_at=_utc_now(),
            reason=args.reason,
            evidence=args.evidence,
            changed_files=args.changed_file,
            dataset_rows=dataset_rows,
            manifest=manifest,
            scores=scores,
            report=report,
            source_fingerprints={
                _display_path(path): _fingerprint(path)
                for path in fingerprint_paths
            },
            role="baseline" if args.baseline else "change",
        )

        run_reference = _display_path(run_path)
        if args.baseline:
            history = build_initial_history(run_reference, snapshot)
            comparison = None
        else:
            if not history_path.exists():
                raise RagasChangeTrackingError(
                    "history does not exist; record a baseline first"
                )
            history = _load_json_object(history_path)
            previous_reference = str(
                args.previous_run or history.get("current_run") or ""
            )
            if not previous_reference:
                raise RagasChangeTrackingError("previous run is not configured")
            previous_path = _path(previous_reference)
            previous = _load_json_object(previous_path)
            comparison = compare_runs(
                previous,
                snapshot,
                evidence_change_authorized=args.allow_evidence_change,
            )
            history = append_history_change(
                history,
                previous_run_path=_display_path(previous_path),
                current_run_path=run_reference,
                current_snapshot=snapshot,
                comparison=comparison,
            )
    except (OSError, json.JSONDecodeError, RagasChangeTrackingError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 2

    _atomic_write(run_path, json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(history_path, json.dumps(history, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(markdown_path, render_history_markdown(history))
    if comparison is not None:
        detail_report = build_change_detail_report(
            change=history["changes"][-1],
            previous=previous,
            current=snapshot,
        )
        detail_json_path = _path(args.change_report_root) / f"{args.change_id}.json"
        detail_markdown_path = (
            _path(args.change_report_doc_root) / f"{args.change_id}.md"
        )
        _atomic_write(
            detail_json_path,
            json.dumps(detail_report, ensure_ascii=False, indent=2) + "\n",
        )
        _atomic_write(
            detail_markdown_path, render_change_detail_markdown(detail_report)
        )

    print(f"run={_display_path(run_path)}")
    print(f"history={_display_path(history_path)}")
    print(f"mean={snapshot['summary']['mean']}")
    if comparison is None:
        print("status=baseline_recorded")
        return 0

    summary_delta = comparison["metric_delta"]["summary"]["mean"]
    print(f"mean_delta={summary_delta['delta']}")
    print(f"improved_cases={comparison['case_delta']['improved_count']}")
    print(f"regressed_cases={comparison['case_delta']['regressed_count']}")
    print(f"evidence_changes={comparison['content_delta']['context']['changed_count']}")
    print(f"change_report={_display_path(detail_markdown_path)}")
    print(f"status={'passed' if comparison['gates']['passed'] else 'review_required'}")
    return 0 if comparison["gates"]["passed"] else 1


def _path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RagasChangeTrackingError(f"JSON root must be an object: {path}")
    return value


def _fingerprint(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
