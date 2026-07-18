"""Build immutable RAGAS run snapshots and before/after change records."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from statistics import mean, median
from typing import Any, Iterable


TRACKED_THRESHOLDS = (0.70, 0.80, 0.90, 0.95)
MEANINGFUL_DELTA = 0.02


class RagasChangeTrackingError(ValueError):
    """Raised when evaluation artifacts cannot be compared safely."""


def parse_dataset_jsonl(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise RagasChangeTrackingError(
                f"dataset line {line_number} is not valid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise RagasChangeTrackingError(
                f"dataset line {line_number} must be an object"
            )
        rows.append(value)
    if not rows:
        raise RagasChangeTrackingError("dataset must contain at least one row")
    return rows


def build_run_snapshot(
    *,
    run_id: str,
    recorded_at: str,
    reason: str,
    evidence: Iterable[str],
    changed_files: Iterable[str],
    dataset_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    scores: dict[str, Any],
    report: dict[str, Any],
    source_fingerprints: dict[str, str],
    role: str,
) -> dict[str, Any]:
    manifest_rows = manifest.get("samples")
    score_rows = scores.get("records")
    if not isinstance(manifest_rows, list) or not manifest_rows:
        raise RagasChangeTrackingError("manifest must contain samples")
    if not isinstance(score_rows, list) or not score_rows:
        raise RagasChangeTrackingError("scores must contain records")
    if len(dataset_rows) != len(manifest_rows):
        raise RagasChangeTrackingError(
            "dataset and manifest sample counts must match"
        )

    score_by_id: dict[str, dict[str, Any]] = {}
    for row in score_rows:
        if not isinstance(row, dict):
            continue
        sample_id = str(row.get("sample_id") or "")
        if not sample_id:
            raise RagasChangeTrackingError("score record is missing sample_id")
        if sample_id in score_by_id:
            raise RagasChangeTrackingError(f"duplicate score record: {sample_id}")
        score_by_id[sample_id] = row

    samples: list[dict[str, Any]] = []
    for expected_line, manifest_row in enumerate(manifest_rows, start=1):
        if not isinstance(manifest_row, dict):
            raise RagasChangeTrackingError(
                f"manifest sample #{expected_line} must be an object"
            )
        line = manifest_row.get("line")
        if line != expected_line:
            raise RagasChangeTrackingError(
                "manifest lines must be contiguous and one-based"
            )
        sample_id = str(manifest_row.get("sample_id") or "")
        case_id = str(manifest_row.get("case_id") or "")
        question_type = str(manifest_row.get("question_type") or "")
        if not sample_id or not case_id or not question_type:
            raise RagasChangeTrackingError(
                f"manifest sample #{expected_line} is missing identifiers"
            )
        score_row = score_by_id.get(sample_id)
        if score_row is None:
            raise RagasChangeTrackingError(f"missing score for {sample_id}")
        if score_row.get("status") != "success":
            raise RagasChangeTrackingError(f"score is not successful: {sample_id}")
        score_value = score_row.get("faithfulness")
        if not isinstance(score_value, (int, float)) or not math.isfinite(
            float(score_value)
        ):
            raise RagasChangeTrackingError(f"invalid score for {sample_id}")

        dataset_row = dataset_rows[expected_line - 1]
        required_fields = (
            "user_input",
            "response",
            "retrieved_contexts",
            "reference",
        )
        if any(field not in dataset_row for field in required_fields):
            raise RagasChangeTrackingError(
                f"dataset sample {sample_id} is missing required fields"
            )
        scenario_id = _scenario_id(case_id, question_type)
        samples.append(
            {
                "sample_id": sample_id,
                "case_id": case_id,
                "scenario_id": scenario_id,
                "question_type": question_type,
                "condition": manifest_row.get("condition"),
                "faithfulness": _round(float(score_value)),
                "content": {
                    "user_input": dataset_row["user_input"],
                    "response": dataset_row["response"],
                    "retrieved_contexts": dataset_row["retrieved_contexts"],
                    "reference": dataset_row["reference"],
                },
                "signatures": {
                    "question": _hash_json(dataset_row["user_input"]),
                    "response": _hash_json(dataset_row["response"]),
                    "context": _hash_json(dataset_row["retrieved_contexts"]),
                    "reference": _hash_json(dataset_row["reference"]),
                    "combined": str(manifest_row.get("run_signature") or ""),
                },
            }
        )

    values = [float(sample["faithfulness"]) for sample in samples]
    evaluation = report.get("evaluation") if isinstance(report.get("evaluation"), dict) else {}
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "role": role,
        "recorded_at": recorded_at,
        "reason": reason.strip(),
        "evidence": _clean_text_list(evidence),
        "changed_files": _clean_text_list(changed_files),
        "evaluation": {
            "library": evaluation.get("library", "ragas"),
            "ragas_version": evaluation.get("ragas_version") or scores.get("ragas_version"),
            "metric": evaluation.get("metric", "faithfulness"),
            "model": evaluation.get("model") or scores.get("model"),
            "report_status": report.get("status"),
            "reportable_as_final": bool(report.get("reportable_as_final", False)),
        },
        "source_fingerprints": dict(sorted(source_fingerprints.items())),
        "summary": _metric_summary(values),
        "by_question_type": _group_summary(samples, "question_type"),
        "by_scenario": _group_summary(samples, "scenario_id"),
        "samples": sorted(samples, key=lambda item: item["sample_id"]),
    }


def compare_runs(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    evidence_change_authorized: bool,
) -> dict[str, Any]:
    previous_samples = {
        str(row["sample_id"]): row for row in previous.get("samples", [])
    }
    current_samples = {
        str(row["sample_id"]): row for row in current.get("samples", [])
    }
    previous_ids = set(previous_samples)
    current_ids = set(current_samples)
    matched_ids = sorted(previous_ids & current_ids)
    added_ids = sorted(current_ids - previous_ids)
    removed_ids = sorted(previous_ids - current_ids)

    component_changes: dict[str, list[str]] = {
        "question": [],
        "response": [],
        "context": [],
        "reference": [],
        "combined": [],
    }
    case_changes: list[dict[str, Any]] = []
    for sample_id in matched_ids:
        before = previous_samples[sample_id]
        after = current_samples[sample_id]
        before_signatures = before.get("signatures", {})
        after_signatures = after.get("signatures", {})
        for component in component_changes:
            if before_signatures.get(component) != after_signatures.get(component):
                component_changes[component].append(sample_id)
        before_score = float(before["faithfulness"])
        after_score = float(after["faithfulness"])
        delta = after_score - before_score
        case_changes.append(
            {
                "sample_id": sample_id,
                "question_type": after.get("question_type"),
                "scenario_id": after.get("scenario_id"),
                "before": _round(before_score),
                "after": _round(after_score),
                "delta": _round(delta),
                "direction": _direction(delta),
                "response_changed": sample_id in component_changes["response"],
                "evidence_changed": (
                    sample_id in component_changes["context"]
                    or sample_id in component_changes["reference"]
                ),
            }
        )

    improved = [row for row in case_changes if row["delta"] > 0]
    regressed = [row for row in case_changes if row["delta"] < 0]
    meaningful_improved = [
        row for row in case_changes if row["delta"] >= MEANINGFUL_DELTA
    ]
    meaningful_regressed = [
        row for row in case_changes if row["delta"] <= -MEANINGFUL_DELTA
    ]
    mean_delta = _delta(
        previous.get("summary", {}).get("mean"),
        current.get("summary", {}).get("mean"),
    )
    evidence_changed_ids = sorted(
        set(component_changes["context"]) | set(component_changes["reference"])
    )
    coverage_complete = (
        current.get("summary", {}).get("sample_count", 0) > 0
        and not added_ids
        and not removed_ids
    )
    gates = {
        "coverage_complete": coverage_complete,
        "mean_not_regressed": mean_delta is not None and mean_delta >= 0,
        "no_meaningful_case_regression": not meaningful_regressed,
        "evidence_change_declared": (
            not evidence_changed_ids or evidence_change_authorized
        ),
    }
    return {
        "previous_run_id": previous.get("run_id"),
        "current_run_id": current.get("run_id"),
        "sample_set": {
            "matched": len(matched_ids),
            "added": added_ids,
            "removed": removed_ids,
        },
        "metric_delta": {
            "summary": _summary_delta(previous.get("summary", {}), current.get("summary", {})),
            "by_question_type": _group_delta(
                previous.get("by_question_type", {}),
                current.get("by_question_type", {}),
            ),
            "by_scenario": _group_delta(
                previous.get("by_scenario", {}), current.get("by_scenario", {})
            ),
        },
        "content_delta": {
            component: {
                "changed_count": len(sample_ids),
                "sample_ids": sample_ids,
            }
            for component, sample_ids in component_changes.items()
        },
        "case_delta": {
            "improved_count": len(improved),
            "regressed_count": len(regressed),
            "unchanged_count": len(case_changes) - len(improved) - len(regressed),
            "meaningful_improved_count": len(meaningful_improved),
            "meaningful_regressed_count": len(meaningful_regressed),
            "top_improvements": sorted(
                improved, key=lambda row: row["delta"], reverse=True
            )[:10],
            "top_regressions": sorted(regressed, key=lambda row: row["delta"])[:10],
        },
        "evidence_change_authorized": evidence_change_authorized,
        "gates": {
            **gates,
            "passed": all(gates.values()),
        },
    }


def build_initial_history(run_path: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "baseline_run": run_path,
        "current_run": run_path,
        "baseline": {
            "run_id": snapshot["run_id"],
            "recorded_at": snapshot["recorded_at"],
            "summary": snapshot["summary"],
        },
        "changes": [],
    }


def append_history_change(
    history: dict[str, Any],
    *,
    previous_run_path: str,
    current_run_path: str,
    current_snapshot: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    updated = json.loads(json.dumps(history, ensure_ascii=False))
    changes = updated.get("changes")
    if not isinstance(changes, list):
        raise RagasChangeTrackingError("history changes must be an array")
    if any(
        str(change.get("change_id")) == current_snapshot["run_id"]
        for change in changes
        if isinstance(change, dict)
    ):
        raise RagasChangeTrackingError(
            f"change id already exists: {current_snapshot['run_id']}"
        )
    changes.append(
        {
            "change_id": current_snapshot["run_id"],
            "recorded_at": current_snapshot["recorded_at"],
            "reason": current_snapshot["reason"],
            "evidence": current_snapshot["evidence"],
            "changed_files": current_snapshot["changed_files"],
            "previous_run": previous_run_path,
            "current_run": current_run_path,
            "comparison": comparison,
        }
    )
    updated["current_run"] = current_run_path
    return updated


def render_history_markdown(history: dict[str, Any]) -> str:
    baseline = history.get("baseline", {})
    summary = baseline.get("summary", {})
    lines = [
        "# RAGAS 변경 전후 지표 이력",
        "",
        "> 모든 수정은 근거·답변·점수의 전후 변화를 함께 기록합니다. 자동평가 잠정 결과이며 사람 검수 전 최종 성능으로 발표하지 않습니다.",
        "",
        "## 고정 기준선",
        "",
        f"- 실행 ID: `{baseline.get('run_id', '-')}`",
        f"- 기록 시각: {baseline.get('recorded_at', '-')}",
        f"- 표본: {summary.get('sample_count', '-')}건",
        f"- 평균 Faithfulness: {_display(summary.get('mean'))}",
        f"- 중앙값: {_display(summary.get('median'))}",
        f"- 0.80 이상: {_threshold_display(summary, '0.80')}",
        f"- 0.95 이상: {_threshold_display(summary, '0.95')}",
        "",
        "## 변경 이력",
        "",
        "| 변경 ID | 이유 | 평균 전 → 후 | 변화 | 개선/회귀 | 근거 변경 | 판정 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    changes = history.get("changes", [])
    if not changes:
        lines.append("| - | 기준선만 등록됨 | - | - | - | - | - |")
    for change in changes:
        comparison = change.get("comparison", {})
        summary_delta = comparison.get("metric_delta", {}).get("summary", {})
        cases = comparison.get("case_delta", {})
        content = comparison.get("content_delta", {})
        evidence_count = len(
            set(content.get("context", {}).get("sample_ids", []))
            | set(content.get("reference", {}).get("sample_ids", []))
        )
        before = summary_delta.get("mean", {}).get("before")
        after = summary_delta.get("mean", {}).get("after")
        delta = summary_delta.get("mean", {}).get("delta")
        lines.append(
            f"| `{change.get('change_id')}` | {_escape_cell(change.get('reason'))} | "
            f"{_display(before)} → {_display(after)} | {_signed(delta)} | "
            f"{cases.get('improved_count', 0)}/{cases.get('regressed_count', 0)} | "
            f"{evidence_count}건 | "
            f"{'통과' if comparison.get('gates', {}).get('passed') else '확인 필요'} |"
        )

    if changes:
        latest = changes[-1]
        comparison = latest.get("comparison", {})
        lines.extend(
            [
                "",
                "## 최근 변경 상세",
                "",
                f"- 변경 ID: `{latest.get('change_id')}`",
                f"- 변경 이유: {latest.get('reason', '-')}",
                f"- 판단 근거: {', '.join(latest.get('evidence', [])) or '-'}",
                f"- 변경 파일: {', '.join(latest.get('changed_files', [])) or '-'}",
                "",
                "### 질문 유형별 평균 변화",
                "",
                "| 질문 유형 | 이전 | 이후 | 변화 |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for key, value in comparison.get("metric_delta", {}).get(
            "by_question_type", {}
        ).items():
            lines.append(
                f"| {key} | {_display(value.get('before'))} | "
                f"{_display(value.get('after'))} | {_signed(value.get('delta'))} |"
            )
    lines.append("")
    return "\n".join(lines)


def build_change_detail_report(
    *,
    change: dict[str, Any],
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Build a self-contained before/after report for one recorded change."""

    comparison = change.get("comparison")
    if not isinstance(comparison, dict):
        raise RagasChangeTrackingError("change is missing comparison data")
    previous_samples = {
        str(row["sample_id"]): row for row in previous.get("samples", [])
    }
    current_samples = {
        str(row["sample_id"]): row for row in current.get("samples", [])
    }
    sample_rows: list[dict[str, Any]] = []
    for sample_id in sorted(set(previous_samples) & set(current_samples)):
        before = previous_samples[sample_id]
        after = current_samples[sample_id]
        before_signatures = before.get("signatures", {})
        after_signatures = after.get("signatures", {})
        question_changed = before_signatures.get("question") != after_signatures.get("question")
        response_changed = before_signatures.get("response") != after_signatures.get("response")
        context_changed = before_signatures.get("context") != after_signatures.get("context")
        reference_changed = before_signatures.get("reference") != after_signatures.get("reference")
        score_delta = _round(
            float(after["faithfulness"]) - float(before["faithfulness"])
        )
        if not any(
            (
                question_changed,
                response_changed,
                context_changed,
                reference_changed,
                score_delta != 0,
            )
        ):
            continue
        before_content = before.get("content", {})
        after_content = after.get("content", {})
        sample_rows.append(
            {
                "sample_id": sample_id,
                "scenario_id": after.get("scenario_id"),
                "question_type": after.get("question_type"),
                "score": {
                    "before": before.get("faithfulness"),
                    "after": after.get("faithfulness"),
                    "delta": score_delta,
                },
                "changes": {
                    "question": question_changed,
                    "response": response_changed,
                    "context": context_changed,
                    "reference": reference_changed,
                },
                "before": {
                    "user_input": before_content.get("user_input"),
                    "response": before_content.get("response"),
                    "retrieved_contexts": before_content.get("retrieved_contexts"),
                    "reference": before_content.get("reference"),
                },
                "after": {
                    "user_input": after_content.get("user_input"),
                    "response": after_content.get("response"),
                    "retrieved_contexts": after_content.get("retrieved_contexts"),
                    "reference": after_content.get("reference"),
                },
            }
        )

    return {
        "schema_version": "1.0",
        "change_id": change.get("change_id"),
        "recorded_at": change.get("recorded_at"),
        "reason": change.get("reason"),
        "evidence": change.get("evidence", []),
        "changed_files": change.get("changed_files", []),
        "previous_run": change.get("previous_run"),
        "current_run": change.get("current_run"),
        "evaluation": current.get("evaluation", {}),
        "before_summary": previous.get("summary", {}),
        "after_summary": current.get("summary", {}),
        "comparison": comparison,
        "changed_samples": sample_rows,
    }


def render_change_detail_markdown(report: dict[str, Any]) -> str:
    comparison = report["comparison"]
    summary_delta = comparison["metric_delta"]["summary"]
    cases = comparison["case_delta"]
    content = comparison["content_delta"]
    lines = [
        f"# RAGAS 변경 리포트: {report['change_id']}",
        "",
        "> 적용 전·적용 후의 답변, 근거, 점수 변화를 한 변경 단위로 기록한 잠정 자동평가 리포트입니다.",
        "",
        "## 변경 개요",
        "",
        f"- 변경 이유: {report.get('reason') or '-'}",
        f"- 판단 근거: {', '.join(report.get('evidence', [])) or '-'}",
        f"- 변경 파일: {', '.join(report.get('changed_files', [])) or '-'}",
        f"- 이전 실행: `{report.get('previous_run')}`",
        f"- 이후 실행: `{report.get('current_run')}`",
        "",
        "## 핵심 지표 전후",
        "",
        "| 지표 | 적용 전 | 적용 후 | 변화 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, label in (
        ("mean", "평균 Faithfulness"),
        ("median", "중앙값"),
        ("minimum", "최저값"),
        ("maximum", "최고값"),
    ):
        value = summary_delta[key]
        lines.append(
            f"| {label} | {_display(value.get('before'))} | "
            f"{_display(value.get('after'))} | {_signed(value.get('delta'))} |"
        )
    for threshold in ("0.80", "0.95"):
        value = summary_delta["thresholds"][threshold]["passed"]
        lines.append(
            f"| {threshold} 이상 건수 | {value.get('before')} | "
            f"{value.get('after')} | {_signed(value.get('delta'))} |"
        )

    lines.extend(
        [
            "",
            "## 변경 범위와 회귀",
            "",
            f"- 답변 변경: {content['response']['changed_count']}건",
            f"- 검색 근거 변경: {content['context']['changed_count']}건",
            f"- 기준답안 변경: {content['reference']['changed_count']}건",
            f"- 개선/회귀/동일: {cases['improved_count']}/{cases['regressed_count']}/{cases['unchanged_count']}건",
            f"- 자동 판정: {'통과' if comparison['gates']['passed'] else '확인 필요'}",
            "",
            "## 질문 유형별 평균 전후",
            "",
            "| 질문 유형 | 적용 전 | 적용 후 | 변화 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for key, value in comparison["metric_delta"]["by_question_type"].items():
        lines.append(
            f"| {key} | {_display(value.get('before'))} | "
            f"{_display(value.get('after'))} | {_signed(value.get('delta'))} |"
        )

    changed_samples = report.get("changed_samples", [])
    lines.extend(
        [
            "",
            "## 변경·점수 변화 사례",
            "",
            "| 사례 | 유형 | 점수 전 → 후 | 변화 | 답변 | 근거 |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    if not changed_samples:
        lines.append("| - | - | - | - | 변경 없음 | 변경 없음 |")
    for row in sorted(
        changed_samples, key=lambda item: item["score"]["delta"], reverse=True
    ):
        lines.append(
            f"| `{row['sample_id']}` | {row.get('question_type')} | "
            f"{_display(row['score']['before'])} → {_display(row['score']['after'])} | "
            f"{_signed(row['score']['delta'])} | "
            f"{'변경' if row['changes']['response'] else '동일'} | "
            f"{'변경' if row['changes']['context'] or row['changes']['reference'] else '동일'} |"
        )

    response_samples = [
        row for row in changed_samples if row.get("changes", {}).get("response")
    ]
    if response_samples:
        representative = max(
            response_samples, key=lambda item: item["score"]["delta"]
        )
        lines.extend(
            [
                "",
                "## 대표 답변 전후",
                "",
                f"사례: `{representative['sample_id']}`",
                "",
                "### 적용 전",
                "",
                str(representative["before"].get("response") or "-"),
                "",
                "### 적용 후",
                "",
                str(representative["after"].get("response") or "-"),
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _metric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        raise RagasChangeTrackingError("run must contain scored samples")
    return {
        "sample_count": len(values),
        "mean": _round(mean(values)),
        "median": _round(median(values)),
        "minimum": _round(min(values)),
        "maximum": _round(max(values)),
        "thresholds": {
            f"{threshold:.2f}": {
                "passed": sum(value >= threshold for value in values),
                "pass_rate": _round(
                    sum(value >= threshold for value in values) / len(values)
                ),
            }
            for threshold in TRACKED_THRESHOLDS
        },
    }


def _group_summary(samples: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        grouped[str(sample.get(field) or "unknown")].append(
            float(sample["faithfulness"])
        )
    return {
        key: {"sample_count": len(values), "mean": _round(mean(values))}
        for key, values in sorted(grouped.items())
    }


def _summary_delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: _value_delta(previous.get(key), current.get(key))
        for key in ("mean", "median", "minimum", "maximum")
    }
    result["thresholds"] = {}
    for threshold in sorted(
        set(previous.get("thresholds", {})) | set(current.get("thresholds", {}))
    ):
        before = previous.get("thresholds", {}).get(threshold, {})
        after = current.get("thresholds", {}).get(threshold, {})
        result["thresholds"][threshold] = {
            "passed": _value_delta(before.get("passed"), after.get("passed")),
            "pass_rate": _value_delta(
                before.get("pass_rate"), after.get("pass_rate")
            ),
        }
    return result


def _group_delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _value_delta(
            previous.get(key, {}).get("mean"), current.get(key, {}).get("mean")
        )
        for key in sorted(set(previous) | set(current))
    }


def _value_delta(before: Any, after: Any) -> dict[str, Any]:
    return {
        "before": before,
        "after": after,
        "delta": _delta(before, after),
    }


def _delta(before: Any, after: Any) -> float | None:
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return None
    return _round(float(after) - float(before))


def _direction(delta: float) -> str:
    if delta > 0:
        return "improved"
    if delta < 0:
        return "regressed"
    return "unchanged"


def _scenario_id(case_id: str, question_type: str) -> str:
    suffix = f"__{question_type}"
    return case_id[: -len(suffix)] if case_id.endswith(suffix) else case_id


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clean_text_list(values: Iterable[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _round(value: float) -> float:
    return round(float(value), 4)


def _display(value: Any) -> str:
    return "-" if not isinstance(value, (int, float)) else f"{float(value):.4f}"


def _signed(value: Any) -> str:
    return "-" if not isinstance(value, (int, float)) else f"{float(value):+.4f}"


def _threshold_display(summary: dict[str, Any], threshold: str) -> str:
    value = summary.get("thresholds", {}).get(threshold, {})
    passed = value.get("passed")
    rate = value.get("pass_rate")
    if passed is None or rate is None:
        return "-"
    return f"{passed}건 ({float(rate) * 100:.2f}%)"


def _escape_cell(value: Any) -> str:
    return str(value or "-").replace("|", "\\|").replace("\n", " ")
