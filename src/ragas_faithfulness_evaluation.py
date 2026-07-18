"""Prepare and summarize RAGAS faithfulness evaluation inputs.

The human-reviewed Gold Set remains the source for retrieval metrics.  This
module evaluates the already-saved explanation A/B responses against the
bounded recommendation evidence that belongs to each case.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from statistics import mean, median
from typing import Any, Iterable


class RagasEvaluationInputError(ValueError):
    """Raised when stored evaluation data cannot be matched safely."""


def prepare_faithfulness_samples(
    case_document: dict[str, Any],
    result_document: dict[str, Any],
    *,
    conditions: Iterable[str] = ("after",),
) -> list[dict[str, Any]]:
    """Join saved responses to their evidence and return RAGAS-ready samples."""

    requested_conditions = {str(value).strip().casefold() for value in conditions}
    if not requested_conditions or not requested_conditions <= {"before", "after"}:
        raise RagasEvaluationInputError("conditions must contain before and/or after")

    cases = case_document.get("cases")
    records = result_document.get("records")
    if not isinstance(cases, list) or not cases:
        raise RagasEvaluationInputError("case document must contain a non-empty cases array")
    if not isinstance(records, list) or not records:
        raise RagasEvaluationInputError("result document must contain a non-empty records array")

    case_by_id: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise RagasEvaluationInputError(f"case #{index} must be an object")
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            raise RagasEvaluationInputError(f"case #{index} is missing id")
        if case_id in case_by_id:
            raise RagasEvaluationInputError(f"duplicate case id: {case_id}")
        case_by_id[case_id] = case

    samples: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise RagasEvaluationInputError(f"record #{index} must be an object")
        condition = str(record.get("condition") or "").strip().casefold()
        if condition not in requested_conditions:
            continue
        case_id = str(record.get("case_id") or "").strip()
        case = case_by_id.get(case_id)
        if case is None:
            raise RagasEvaluationInputError(f"record references unknown case: {case_id}")
        key = (case_id, condition)
        if key in seen:
            raise RagasEvaluationInputError(f"duplicate response for {case_id}/{condition}")
        seen.add(key)

        if str(record.get("status") or "").casefold() != "success":
            continue
        response = record.get("response")
        answer = str(response.get("answer") or "").strip() if isinstance(response, dict) else ""
        question = str(case.get("question") or "").strip()
        contexts = reference_contexts(case)
        if not question or not answer or not contexts:
            raise RagasEvaluationInputError(
                f"case {case_id}/{condition} is missing question, answer, or evidence context"
            )

        sample = {
            "sample_id": f"{case_id}__{condition}",
            "case_id": case_id,
            "condition": condition,
            "scenario_id": str(case.get("scenario_id") or ""),
            "question_type": str(case.get("question_type") or ""),
            "user_input": question,
            "response": answer,
            "retrieved_contexts": contexts,
            "reference": reference_answer(case),
        }
        sample["run_signature"] = sample_signature(sample)
        samples.append(sample)

    if not samples:
        raise RagasEvaluationInputError("no successful records matched the requested conditions")
    return samples


def reference_contexts(case: dict[str, Any]) -> list[str]:
    """Build bounded evidence chunks from the exact context used by the case."""

    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    context = (
        case.get("recommendation_context")
        if isinstance(case.get("recommendation_context"), dict)
        else {}
    )
    selected = context.get("selected_place") if isinstance(context.get("selected_place"), dict) else {}
    recommendation = (
        context.get("recommendation")
        if isinstance(context.get("recommendation"), dict)
        else {}
    )
    traveler = context.get("traveler_summary") if isinstance(context.get("traveler_summary"), dict) else {}

    chunks: list[str] = []
    mode = str(context.get("mode") or "").strip().casefold()
    if case.get("question_type") == "mode_distinction" and mode in {"static", "runtime"}:
        mode_chunk = {
            "source_field": "recommendation_context.mode",
            "mode": mode,
            "mode_meaning": (
                "입력 조건과 가장 가까운 사전 계산 시나리오이며 실시간 개인별 재계산이 아닙니다."
                if mode == "static"
                else "현재 입력을 사용해 실행 시점에 계산한 결과입니다."
            ),
            "generated_at": context.get("generated_at"),
            "engine": context.get("engine"),
        }
        chunks.append(_compact_json(mode_chunk, 2000))

    selected_chunk = {
        "selected_place_name": case.get("selected_place_name"),
        "selected_place": selected,
        "score": expected.get("score"),
        "fit_reasons": (expected.get("reasons") or {}).get("fit", []),
        "checks": expected.get("checks", []),
        "sources": expected.get("sources", []),
    }
    chunks.append(_compact_json(selected_chunk, 9000))

    route = (recommendation.get("course") or {}).get("route", [])
    route_chunk = {
        "allowed_course_place_names": expected.get("allowed_course_place_names", []),
        "excluded_place_names": expected.get("excluded_place_names", []),
        "route": route,
        "course_score": expected.get("course_score"),
        "course_fit": (expected.get("reasons") or {}).get("course_fit", []),
        "course_deductions": (expected.get("reasons") or {}).get("course_deductions", []),
    }
    chunks.append(_compact_json(route_chunk, 9000))

    conditions_chunk = {
        "traveler_summary": traveler or expected.get("conditions", {}),
        "expected_user_conditions": case.get("expected_user_conditions", []),
        "expected_evidence": case.get("expected_evidence", []),
        "exclusion_basis": expected.get("exclusion_basis", []),
        "limitations": expected.get("limitations", []),
    }
    chunks.append(_compact_json(conditions_chunk, 9000))
    return [chunk for chunk in chunks if chunk and chunk != "{}"]


def reference_answer(case: dict[str, Any]) -> str:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    selected_name = str(case.get("selected_place_name") or "선택 장소")
    evidence = [str(value) for value in case.get("expected_evidence") or [] if value]
    checks = [str(value) for value in expected.get("checks") or [] if value]
    allowed = [str(value) for value in expected.get("allowed_course_place_names") or [] if value]
    parts = [f"{selected_name}의 추천 근거를 사용자 조건과 연결해 설명한다."]
    if evidence:
        parts.append("근거: " + " ".join(evidence[:5]))
    if checks:
        parts.append("방문 전 확인: " + ", ".join(checks[:8]))
    if allowed:
        parts.append("허용된 코스 장소: " + ", ".join(allowed[:4]))
    return " ".join(parts)


def build_faithfulness_report(
    samples: Iterable[dict[str, Any]],
    score_records: Iterable[dict[str, Any]],
    *,
    generated_at: date,
    model: str,
    ragas_version: str,
    threshold: float = 0.95,
) -> dict[str, Any]:
    sample_rows = list(samples)
    scores = list(score_records)
    sample_by_id = {sample["sample_id"]: sample for sample in sample_rows}
    successful = [
        row
        for row in scores
        if row.get("status") == "success"
        and isinstance(row.get("faithfulness"), (int, float))
        and math.isfinite(float(row["faithfulness"]))
    ]
    errors = [row for row in scores if row.get("status") != "success"]

    values = [float(row["faithfulness"]) for row in successful]
    by_condition = _group_summary(successful, sample_by_id, "condition", threshold)
    by_question_type = _group_summary(successful, sample_by_id, "question_type", threshold)
    lowest = sorted(successful, key=lambda row: float(row["faithfulness"]))[:10]

    complete = len(successful) == len(sample_rows) and not errors
    return {
        "schema_version": "1.0",
        "generated_at": generated_at.isoformat(),
        "status": "complete_provisional" if complete else "incomplete_provisional",
        "reportable_as_final": False,
        "metric_status": "provisional_automatic_metric",
        "warning": (
            "RAGAS 자동 심사 결과이며 사람 검수 Gold Set이 승인되기 전에는 최종 성능으로 발표하지 않는다."
        ),
        "evaluation": {
            "library": "ragas",
            "ragas_version": ragas_version,
            "metric": "faithfulness",
            "model": model,
            "threshold": threshold,
            "conditions": sorted({sample["condition"] for sample in sample_rows}),
            "context_interpretation": (
                "after는 실제 제공 추천 컨텍스트, before는 동일 기준 근거에 대한 진단 비교로만 해석한다."
            ),
        },
        "coverage": {
            "target_samples": len(sample_rows),
            "successful_samples": len(successful),
            "error_samples": len(errors),
            "coverage_rate": _ratio(len(successful), len(sample_rows)),
        },
        "summary": {
            "mean": _round(mean(values)) if values else None,
            "median": _round(median(values)) if values else None,
            "minimum": _round(min(values)) if values else None,
            "maximum": _round(max(values)) if values else None,
            "passed_samples": sum(value >= threshold for value in values),
            "pass_rate": _ratio(sum(value >= threshold for value in values), len(values)),
        },
        "by_condition": by_condition,
        "by_question_type": by_question_type,
        "lowest_cases": [
            {
                "sample_id": row["sample_id"],
                "case_id": sample_by_id[row["sample_id"]]["case_id"],
                "condition": sample_by_id[row["sample_id"]]["condition"],
                "question_type": sample_by_id[row["sample_id"]]["question_type"],
                "faithfulness": _round(float(row["faithfulness"])),
                "passed": float(row["faithfulness"]) >= threshold,
            }
            for row in lowest
        ],
        "errors": [
            {
                "sample_id": row.get("sample_id"),
                "error_type": row.get("error_type", "evaluation_error"),
            }
            for row in errors
        ],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    coverage = report["coverage"]
    lines = [
        "# RAGAS Faithfulness 자동검증 보고서",
        "",
        f"기준일: {report['generated_at']}",
        "",
        "> 자동평가·잠정 결과입니다. 사람 검수 Gold Set 승인 전에는 최종 성능으로 발표할 수 없습니다.",
        "",
        "## 결과 요약",
        "",
        "| 항목 | 값 |",
        "| --- | ---: |",
        f"| 평가 성공 | {coverage['successful_samples']}/{coverage['target_samples']} |",
        f"| 평균 Faithfulness | {_display(summary['mean'])} |",
        f"| 중앙값 | {_display(summary['median'])} |",
        f"| 최소값 | {_display(summary['minimum'])} |",
        f"| 기준 통과율 | {_display(summary['pass_rate'])} |",
        "",
        "## 해석",
        "",
        "- Faithfulness는 생성 답변의 주장 중 제공 근거로 뒷받침되는 비율을 0~1로 평가합니다.",
        "- 이 보고서는 저장된 GPT 설명과 해당 케이스의 추천 근거를 비교합니다.",
        "- 추천 순위 정확도는 별도의 사람 승인 Gold Set과 Recall@4로 검증해야 합니다.",
        "",
        "## 우선 확인할 낮은 점수 사례",
        "",
        "| 케이스 | 조건 | 질문 유형 | 점수 | 통과 |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in report.get("lowest_cases", []):
        lines.append(
            f"| {row['case_id']} | {row['condition']} | {row['question_type']} | "
            f"{row['faithfulness']:.4f} | {'예' if row['passed'] else '아니오'} |"
        )
    lines.extend(
        [
            "",
            "## 다음 단계",
            "",
            "1. 기준 미달 사례의 문장과 근거를 대조합니다.",
            "2. 사람 검수 Gold Set을 확정한 뒤 Recall@4와 필수 조건 위반률을 계산합니다.",
            "3. 최종 발표에는 자동평가와 사람평가를 분리해 표시합니다.",
            "",
        ]
    )
    return "\n".join(lines)


def sample_signature(sample: dict[str, Any]) -> str:
    payload = {
        "user_input": sample.get("user_input"),
        "response": sample.get("response"),
        "retrieved_contexts": sample.get("retrieved_contexts"),
        "reference": sample.get("reference"),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ragas_dataset_rows(samples: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "user_input": sample["user_input"],
            "retrieved_contexts": sample["retrieved_contexts"],
            "response": sample["response"],
            "reference": sample["reference"],
        }
        for sample in samples
    ]


def _group_summary(
    rows: list[dict[str, Any]],
    sample_by_id: dict[str, dict[str, Any]],
    field: str,
    threshold: float,
) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        sample = sample_by_id[row["sample_id"]]
        grouped[str(sample.get(field) or "unknown")].append(float(row["faithfulness"]))
    return {
        key: {
            "sample_count": len(values),
            "mean": _round(mean(values)),
            "pass_rate": _ratio(sum(value >= threshold for value in values), len(values)),
        }
        for key, values in sorted(grouped.items())
    }


def _compact_json(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text[:limit]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return _round(numerator / denominator)


def _round(value: float) -> float:
    return round(float(value), 4)


def _display(value: Any) -> str:
    return "-" if value is None else f"{float(value):.4f}"
