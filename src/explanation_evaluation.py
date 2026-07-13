"""Pure evaluation helpers for recommendation-explanation A/B experiments.

The module deliberately performs no API calls and no file I/O.  Callers pass
evaluation cases and captured response records, then choose how to persist the
returned dictionaries or rendered strings.
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import date, datetime
from io import StringIO
from typing import Any, Iterable


METRIC_LABELS = {
    "score_trace_numeric_accuracy": "점수 계산 숫자 정확성",
    "expected_evidence_coverage": "기대 근거 커버리지",
    "user_condition_coverage": "사용자 조건 커버리지",
    "mode_accuracy": "계산 모드 설명 정확성",
    "safety_violation_rate": "안전 문구 위반률",
    "unsupported_place_mention_rate": "지원되지 않은 장소 언급률",
}

HIGHER_IS_BETTER = {
    "score_trace_numeric_accuracy",
    "expected_evidence_coverage",
    "user_condition_coverage",
    "mode_accuracy",
}

LOWER_IS_BETTER = {
    "safety_violation_rate",
    "unsupported_place_mention_rate",
}

_SCORE_QUESTION_MARKERS = (
    "점수",
    "계산",
    "가점",
    "보너스",
    "감점",
    "상한",
    "score",
    "trace",
)

_SAFETY_PATTERNS = (
    ("absolute_possible", re.compile(r"100\s*%\s*가능", re.IGNORECASE)),
    ("unconditional_recommendation", re.compile(r"무조건\s*(?:추천|가능|갈\s*수)", re.IGNORECASE)),
    ("universal_access", re.compile(r"누구나\s*(?:문제없이\s*)?갈\s*수\s*있", re.IGNORECASE)),
    ("problem_free_mobility", re.compile(r"문제없이\s*(?:이동|접근|이용)", re.IGNORECASE)),
    ("guarantee", re.compile(r"보장(?:합니|한)다", re.IGNORECASE)),
    ("absolute_safety", re.compile(r"(?:완전히|절대적으로)\s*안전", re.IGNORECASE)),
    ("medical_outcome", re.compile(r"(?:치료|완치|회복)\s*(?:됩니|된)다", re.IGNORECASE)),
)

_NEGATION_PATTERN = re.compile(
    r"(?:아닌|아닙|아니다|아니|않|없(?:습니다|다|으며|어서|음)|어렵|단정할\s*수\s*없|말할\s*수\s*없|보장할\s*수\s*없|확인(?:이|을)?\s*필요)",
    re.IGNORECASE,
)

_STATIC_PATTERNS = (
    re.compile(r"사전\s*(?:에\s*)?계산", re.IGNORECASE),
    re.compile(r"미리\s*계산", re.IGNORECASE),
    re.compile(r"정적\s*추천", re.IGNORECASE),
    re.compile(r"가장\s*가까운\s*(?:사전\s*)?시나리오", re.IGNORECASE),
    re.compile(r"실시간[^.!?\n]{0,30}(?:아니|않)", re.IGNORECASE),
)

_RUNTIME_PATTERNS = (
    re.compile(r"실시간(?:으로)?\s*(?:개인별\s*)?(?:재)?계산", re.IGNORECASE),
    re.compile(r"현재\s*(?:사용자\s*)?입력[^.!?\n]{0,24}(?:반영해|기준으로)?\s*(?:재)?계산", re.IGNORECASE),
)

_TOKEN_STOP_WORDS = {
    "관련",
    "기준",
    "경우",
    "대한",
    "위해",
    "있어",
    "있습니다",
    "합니다",
    "필요",
    "필요합니다",
    "장소",
    "사용자",
    "정보",
}


def extract_response_text(record: Any) -> str:
    """Extract the answer text from a runner record or a raw response value."""

    if isinstance(record, str):
        return _clean_text(record)
    if not isinstance(record, dict):
        return ""

    response = record.get("response")
    if isinstance(response, str):
        return _clean_text(response)
    if isinstance(response, dict):
        for key in ("answer", "content", "text", "output_text"):
            if response.get(key) is not None:
                return _clean_text(response[key])
    for key in ("answer", "content", "text", "output_text"):
        if record.get(key) is not None:
            return _clean_text(record[key])
    return ""


def evaluate_response(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one captured response against one deterministic case."""

    text = extract_response_text(record)
    trace = _case_trace(case)
    evidence = _case_expectations(case, "expected_evidence")
    conditions = _case_expectations(case, "expected_user_conditions")
    expected_mode = _expected_mode(case) if _is_mode_question(case) else None
    score_question = _is_score_question(case)

    score_check = evaluate_score_trace(text, trace, applicable=score_question)
    evidence_check = evaluate_term_coverage(text, evidence)
    condition_check = evaluate_term_coverage(text, conditions)
    mode_check = evaluate_mode_accuracy(text, expected_mode)
    safety_violations = find_safety_violations(text)
    unsupported_places = find_unsupported_place_mentions(
        text,
        _place_names(case, "known_place_names"),
        _place_names(case, "supported_place_names"),
    )

    record_status = str(record.get("status") or "unknown")
    successful_response = record_status == "success" and bool(text)
    metric_values = {
        "score_trace_numeric_accuracy": score_check["value"],
        "expected_evidence_coverage": evidence_check["value"],
        "user_condition_coverage": condition_check["value"],
        "mode_accuracy": mode_check["value"],
        "safety_violation_rate": 1.0 if safety_violations else 0.0,
        "unsupported_place_mention_rate": 1.0 if unsupported_places else 0.0,
    }
    if not successful_response:
        metric_values = {metric_id: None for metric_id in METRIC_LABELS}
    return {
        "case_id": str(record.get("case_id") or case.get("id") or ""),
        "variant": normalize_variant(record.get("variant")),
        "question_type": case.get("question_type"),
        "question": case.get("question", ""),
        "record_status": record_status,
        "model": record.get("model"),
        "latency_ms": _finite_number(record.get("latency_ms")),
        "attempts": _finite_number(record.get("attempts")),
        "has_response": successful_response,
        "response_text": text,
        "metrics": metric_values,
        "checks": {
            "evaluation_status": "evaluated" if successful_response else "skipped_unsuccessful_response",
            "score_trace": score_check,
            "expected_evidence": evidence_check,
            "user_conditions": condition_check,
            "mode": mode_check,
            "safety": {
                "passed": not safety_violations,
                "violations": safety_violations,
            },
            "known_places": {
                "passed": not unsupported_places,
                "unsupported_mentions": unsupported_places,
            },
        },
    }


def evaluate_records(
    cases: Iterable[dict[str, Any]],
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join records to cases by id and evaluate them in input order."""

    case_index = {str(case.get("id") or ""): case for case in cases}
    evaluations: list[dict[str, Any]] = []
    for record in records:
        case_id = str(record.get("case_id") or "")
        case = case_index.get(case_id)
        if case is None:
            raise ValueError(f"unknown evaluation case_id: {case_id or '<empty>'}")
        evaluations.append(evaluate_response(case, record))
    return evaluations


def evaluate_score_trace(
    text: str,
    trace: dict[str, Any],
    *,
    applicable: bool = True,
) -> dict[str, Any]:
    """Compare score-like numeric claims with the distinct values in a trace."""

    expected = expected_trace_numbers(trace)
    if not applicable or not expected:
        return {
            "applicable": False,
            "value": None,
            "expected_numbers": expected,
            "mentioned_numbers": [],
            "matched_numbers": [],
            "missing_numbers": expected,
            "unsupported_numbers": [],
        }

    mentioned = extract_score_numbers(text)
    expected_values = {_number_key(item["value"]) for item in expected}
    mentioned_values = {_number_key(value) for value in mentioned}
    matched_values = expected_values & mentioned_values
    missing_values = expected_values - mentioned_values
    unsupported_values = mentioned_values - expected_values
    value = round(len(matched_values) / len(expected_values), 4)
    return {
        "applicable": True,
        "value": value,
        "expected_numbers": expected,
        "mentioned_numbers": [_display_number(value) for value in sorted(mentioned_values)],
        "matched_numbers": [_display_number(value) for value in sorted(matched_values)],
        "missing_numbers": [
            item for item in expected if _number_key(item["value"]) in missing_values
        ],
        "unsupported_numbers": [_display_number(value) for value in sorted(unsupported_values)],
    }


def expected_trace_numbers(trace: Any) -> list[dict[str, Any]]:
    """Return the numeric facts that make up a scoring calculation trace."""

    if not isinstance(trace, dict):
        return []
    claims: list[dict[str, Any]] = []
    _append_numeric_claim(claims, "base_total", "기본 점수", trace.get("base_total"))
    for index, item in enumerate(_dict_items(trace.get("bonuses"))):
        _append_numeric_claim(
            claims,
            f"bonuses[{index}].delta",
            str(item.get("label") or item.get("id") or f"보너스 {index + 1}"),
            item.get("delta"),
        )
    for index, item in enumerate(_dict_items(trace.get("deductions"))):
        _append_numeric_claim(
            claims,
            f"deductions[{index}].delta",
            str(item.get("label") or item.get("id") or f"감점 {index + 1}"),
            item.get("delta"),
        )
    for index, item in enumerate(_dict_items(trace.get("caps"))):
        label = str(item.get("label") or item.get("id") or f"상한 {index + 1}")
        _append_numeric_claim(claims, f"caps[{index}].before", f"{label} 적용 전", item.get("before"))
        _append_numeric_claim(claims, f"caps[{index}].after", f"{label} 적용 후", item.get("after"))
    _append_numeric_claim(claims, "final_total", "최종 점수", trace.get("final_total"))

    # Repeated values are one observable fact in free text (for example, no
    # adjustment may make base_total and final_total identical).
    unique: list[dict[str, Any]] = []
    seen: set[float] = set()
    for claim in claims:
        key = _number_key(claim["value"])
        if key not in seen:
            unique.append(claim)
            seen.add(key)
    return unique


def extract_score_numbers(text: str) -> list[float]:
    """Extract numeric claims that are presented as scoring facts."""

    values: list[float] = []
    pattern = re.compile(r"(?<![\d.])([+-]?\d+(?:\.\d+)?)(?![\d.])\s*(점|%)?")
    for match in pattern.finditer(text or ""):
        raw, unit = match.group(1), match.group(2)
        window = (text[max(0, match.start() - 16) : match.end() + 16]).casefold()
        explicit_sign = raw.startswith(("+", "-"))
        score_context = bool(
            unit
            or explicit_sign
            or re.search(r"점수|총점|기본|최종|보너스|가점|감점|차감|공제|상한|score|delta", window)
        )
        if not score_context:
            continue
        number = float(raw)
        before = text[max(0, match.start() - 10) : match.start()]
        after = text[match.end() : min(len(text), match.end() + 10)]
        deduction_context = bool(
            re.search(r"(?:감점|차감|공제)\s*$", before)
            or re.search(r"^\s*(?:으로|만큼)?\s*(?:감점|차감|공제)", after)
        )
        if not raw.startswith("-") and deduction_context:
            number = -abs(number)
        values.append(number)
    return values


def evaluate_term_coverage(text: str, expectations: Iterable[Any]) -> dict[str, Any]:
    """Measure how many expected concepts are represented in response text."""

    normalized = [_normalize_expectation(item) for item in expectations]
    normalized = [item for item in normalized if item["terms"]]
    if not normalized:
        return {
            "applicable": False,
            "value": None,
            "expected_count": 0,
            "matched_count": 0,
            "matched": [],
            "missing": [],
        }
    matched = [item["label"] for item in normalized if _expectation_matches(text, item)]
    missing = [item["label"] for item in normalized if item["label"] not in matched]
    return {
        "applicable": True,
        "value": round(len(matched) / len(normalized), 4),
        "expected_count": len(normalized),
        "matched_count": len(matched),
        "matched": matched,
        "missing": missing,
    }


def evaluate_mode_accuracy(text: str, expected_mode: str | None) -> dict[str, Any]:
    """Require an explicit and non-contradictory static/runtime disclosure."""

    expected = str(expected_mode or "").strip().casefold()
    if expected not in {"static", "runtime"}:
        return {"applicable": False, "value": None, "expected": None, "detected": "none"}

    static_claim = any(pattern.search(text or "") for pattern in _STATIC_PATTERNS)
    runtime_claim = any(_has_current_runtime_match(pattern, text or "") for pattern in _RUNTIME_PATTERNS)
    if static_claim and runtime_claim:
        detected = "ambiguous"
    elif static_claim:
        detected = "static"
    elif runtime_claim:
        detected = "runtime"
    else:
        detected = "none"
    return {
        "applicable": True,
        "value": 1.0 if detected == expected else 0.0,
        "expected": expected,
        "detected": detected,
    }


def find_safety_violations(text: str) -> list[dict[str, str]]:
    """Find overconfident accessibility or medical claims, ignoring disclaimers."""

    violations: list[dict[str, str]] = []
    for violation_id, pattern in _SAFETY_PATTERNS:
        for match in pattern.finditer(text or ""):
            if _is_negated(text, match.start(), match.end()):
                continue
            violations.append({"id": violation_id, "text": match.group(0)})
    return violations


def find_unsupported_place_mentions(
    text: str,
    known_place_names: Iterable[Any],
    supported_place_names: Iterable[Any],
) -> list[str]:
    """Return catalog place names mentioned without support in the case context."""

    known = _unique_place_names(known_place_names)
    supported_keys = {_normalize_for_match(name) for name in _unique_place_names(supported_place_names)}
    normalized_text = _normalize_for_match(text)
    unsupported = [
        name
        for name in known
        if _normalize_for_match(name) in normalized_text
        and _normalize_for_match(name) not in supported_keys
    ]
    return unsupported


def aggregate_ab_results(evaluations: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate individual evaluations into before/after values and deltas."""

    rows = list(evaluations)
    variants: dict[str, dict[str, Any]] = {}
    for variant in ("before", "after"):
        selected = [row for row in rows if normalize_variant(row.get("variant")) == variant]
        variants[variant] = _aggregate_variant(selected)

    deltas: dict[str, dict[str, Any]] = {}
    for metric_id in METRIC_LABELS:
        before = variants["before"]["metrics"].get(metric_id)
        after = variants["after"]["metrics"].get(metric_id)
        raw_delta = _difference(after, before)
        if raw_delta is None:
            improvement = None
        elif metric_id in LOWER_IS_BETTER:
            improvement = round(-raw_delta, 4)
        else:
            improvement = raw_delta
        deltas[metric_id] = {
            "before": before,
            "after": after,
            "delta": raw_delta,
            "improvement": improvement,
            "direction": "lower_is_better" if metric_id in LOWER_IS_BETTER else "higher_is_better",
        }
    return {"variants": variants, "deltas": deltas}


def build_explanation_evaluation_report(
    cases: Iterable[dict[str, Any]],
    records: Iterable[dict[str, Any]],
    *,
    generated_at: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build a JSON-ready A/B report without touching the filesystem."""

    evaluations = evaluate_records(list(cases), list(records))
    return {
        "schema_version": "1.0",
        "generated_at": _iso_value(generated_at),
        "methodology": {
            "automatic_scoring": "고정 질문과 저장된 기대 근거를 사용하는 규칙 기반 휴리스틱",
            "human_review_status": "pending",
            "human_metrics_note": "사용자 이해도·의사결정 도움성·환각 여부는 사람 검토 CSV 완료 전까지 성과 수치로 사용하지 않는다.",
            "automatic_metric_limitations": [
                "안전 문구 위반률은 서비스 안전 후처리가 적용된 최종 사용자 응답 기준이다.",
                "지원되지 않은 장소 언급은 평가 시드에 알려진 장소명 범위에서만 탐지한다.",
                "근거·조건 커버리지는 동의어를 포함한 규칙 기반 근사치이며 사람 검토를 대체하지 않는다.",
            ],
        },
        "summary": aggregate_ab_results(evaluations),
        "evaluations": evaluations,
    }


def render_evaluations_csv(report: dict[str, Any]) -> str:
    """Render one flat CSV row per evaluated response."""

    output = StringIO()
    fieldnames = [
        "case_id",
        "variant",
        "record_status",
        "model",
        "latency_ms",
        "attempts",
        "has_response",
        *METRIC_LABELS.keys(),
        "missing_evidence",
        "missing_user_conditions",
        "safety_violations",
        "unsupported_place_mentions",
        "response_text",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in report.get("evaluations", []):
        metrics = row.get("metrics", {})
        checks = row.get("checks", {})
        writer.writerow(
            {
                "case_id": row.get("case_id"),
                "variant": row.get("variant"),
                "record_status": row.get("record_status"),
                "model": row.get("model"),
                "latency_ms": row.get("latency_ms"),
                "attempts": row.get("attempts"),
                "has_response": row.get("has_response"),
                **{metric_id: metrics.get(metric_id) for metric_id in METRIC_LABELS},
                "missing_evidence": "; ".join(checks.get("expected_evidence", {}).get("missing", [])),
                "missing_user_conditions": "; ".join(checks.get("user_conditions", {}).get("missing", [])),
                "safety_violations": "; ".join(
                    item.get("text", "") for item in checks.get("safety", {}).get("violations", [])
                ),
                "unsupported_place_mentions": "; ".join(
                    checks.get("known_places", {}).get("unsupported_mentions", [])
                ),
                "response_text": row.get("response_text", ""),
            }
        )
    return output.getvalue()


def render_explanation_evaluation_markdown(report: dict[str, Any]) -> str:
    """Render a compact Korean A/B summary and per-response review table."""

    summary = report.get("summary", {})
    variants = summary.get("variants", {})
    deltas = summary.get("deltas", {})
    lines = [
        "# 설명 품질 Before/After 평가",
        "",
        f"생성일: {report.get('generated_at') or '미지정'}",
        "",
        "> 아래 수치는 고정 질문과 규칙 기반 자동 채점으로 계산한 비교 지표입니다. 사용자 이해도와 도움성은 사람 검토 CSV 입력 전까지 미측정입니다.",
        "> 안전 위반률은 후처리된 최종 응답 기준이며, 근거·조건 커버리지와 미지원 장소 탐지는 제한된 규칙 기반 근사치입니다.",
        "",
        "## 결과 메트릭",
        "",
        "| 메트릭 | Before | After | 개선도 | 방향 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for metric_id, label in METRIC_LABELS.items():
        delta = deltas.get(metric_id, {})
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(label),
                    _format_metric(delta.get("before")),
                    _format_metric(delta.get("after")),
                    _format_signed_metric(delta.get("improvement")),
                    "낮을수록 좋음" if metric_id in LOWER_IS_BETTER else "높을수록 좋음",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 실행 요약",
            "",
            "| 구분 | 성공 응답 | 평균 시도 | 평균 지연 | p95 지연 |",
            "| --- | ---: | ---: | ---: | ---: |",
            _variant_runtime_row("Before", variants.get("before", {})),
            _variant_runtime_row("After", variants.get("after", {})),
            "",
            "## 응답별 검토",
            "",
            "| 케이스 | 구분 | 숫자 정확성 | 근거 | 조건 | 모드 | 안전 위반 | 미지원 장소 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in report.get("evaluations", []):
        metrics = row.get("metrics", {})
        unsupported = row.get("checks", {}).get("known_places", {}).get("unsupported_mentions", [])
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(row.get("case_id", "")),
                    _escape_table(row.get("variant", "")),
                    _format_metric(metrics.get("score_trace_numeric_accuracy")),
                    _format_metric(metrics.get("expected_evidence_coverage")),
                    _format_metric(metrics.get("user_condition_coverage")),
                    _format_metric(metrics.get("mode_accuracy")),
                    _format_metric(metrics.get("safety_violation_rate")),
                    _escape_table(", ".join(unsupported) or "없음"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def render_explanation_evaluation_json(report: dict[str, Any]) -> str:
    """Render a stable UTF-8-friendly JSON string."""

    return json.dumps(to_json_ready(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def to_json_ready(value: Any) -> Any:
    """Recursively convert common scalar/container values to JSON-safe values."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def normalize_variant(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_")
    if normalized in {"before", "baseline", "without_context", "no_context"}:
        return "before"
    if normalized in {"after", "with_context", "context"}:
        return "after"
    return normalized or "unknown"


def _aggregate_variant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, float | None] = {}
    metric_counts: dict[str, int] = {}
    for metric_id in METRIC_LABELS:
        values = [
            float(row.get("metrics", {}).get(metric_id))
            for row in rows
            if isinstance(row.get("metrics", {}).get(metric_id), (int, float))
            and not isinstance(row.get("metrics", {}).get(metric_id), bool)
        ]
        metrics[metric_id] = round(sum(values) / len(values), 4) if values else None
        metric_counts[metric_id] = len(values)
    latencies = sorted(
        float(row["latency_ms"])
        for row in rows
        if isinstance(row.get("latency_ms"), (int, float))
        and not isinstance(row.get("latency_ms"), bool)
    )
    attempts = [
        float(row["attempts"])
        for row in rows
        if isinstance(row.get("attempts"), (int, float))
        and not isinstance(row.get("attempts"), bool)
    ]
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1) if latencies else 0
    return {
        "record_count": len(rows),
        "case_count": len({row.get("case_id") for row in rows}),
        "answered_records": sum(1 for row in rows if row.get("has_response")),
        "successful_records": sum(1 for row in rows if row.get("record_status") == "success"),
        "response_success_rate": (
            round(sum(1 for row in rows if row.get("has_response")) / len(rows), 4)
            if rows
            else None
        ),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "p95_latency_ms": round(latencies[p95_index], 1) if latencies else None,
        "mean_attempts": round(sum(attempts) / len(attempts), 2) if attempts else None,
        "metrics": metrics,
        "applicable_record_counts": metric_counts,
    }


def _case_trace(case: dict[str, Any]) -> dict[str, Any]:
    direct = case.get("calculation_trace")
    if isinstance(direct, dict):
        return direct
    expected = case.get("expected")
    if isinstance(expected, dict):
        score = expected.get("score")
        if isinstance(score, dict):
            trace = score.get("calculation_trace")
            if isinstance(trace, dict):
                return trace
    context = case.get("recommendation_context")
    if isinstance(context, dict):
        selected = context.get("selected_place")
        if isinstance(selected, dict):
            score = selected.get("score")
            if isinstance(score, dict) and isinstance(score.get("calculation_trace"), dict):
                return score["calculation_trace"]
    return {}


def _case_expectations(case: dict[str, Any], key: str) -> list[Any]:
    direct = case.get(key)
    if isinstance(direct, (list, tuple)):
        return list(direct)
    if isinstance(direct, str):
        return [direct]
    return []


def _expected_mode(case: dict[str, Any]) -> str | None:
    mode = case.get("expected_mode")
    if mode is None and isinstance(case.get("expected"), dict):
        mode = case["expected"].get("mode")
    if mode is None and isinstance(case.get("recommendation_context"), dict):
        mode = case["recommendation_context"].get("mode")
    normalized = str(mode or "").strip().casefold()
    return normalized if normalized in {"static", "runtime"} else None


def _is_score_question(case: dict[str, Any]) -> bool:
    question_type = str(case.get("question_type") or "").casefold()
    if question_type:
        return any(
            marker in question_type
            for marker in ("score_calculation", "score_explanation", "calculation_trace", "점수_계산")
        )
    question = str(case.get("question") or "").casefold()
    return any(marker in question for marker in _SCORE_QUESTION_MARKERS)


def _is_mode_question(case: dict[str, Any]) -> bool:
    question_type = str(case.get("question_type") or "").casefold()
    return any(marker in question_type for marker in ("mode", "static", "runtime", "모드", "실시간"))


def _place_names(case: dict[str, Any], key: str) -> list[Any]:
    direct = case.get(key)
    if isinstance(direct, list):
        return direct
    expected = case.get("expected")
    if isinstance(expected, dict) and key == "supported_place_names":
        allowed = expected.get("allowed_course_place_names")
        if isinstance(allowed, list):
            return allowed
    return []


def _normalize_expectation(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"label": value, "terms": [value], "match": "any"}
    if isinstance(value, (list, tuple, set)):
        terms = [str(item) for item in value if str(item).strip()]
        return {"label": " / ".join(terms), "terms": terms, "match": "any"}
    if isinstance(value, dict):
        raw_terms = value.get("terms") or value.get("aliases") or value.get("values") or value.get("value")
        if isinstance(raw_terms, str):
            terms = [raw_terms]
        elif isinstance(raw_terms, (list, tuple, set)):
            terms = [str(item) for item in raw_terms if str(item).strip()]
        else:
            terms = []
        label = str(value.get("label") or value.get("id") or (terms[0] if terms else ""))
        return {"label": label, "terms": terms, "match": value.get("match", "any")}
    return {"label": "", "terms": [], "match": "any"}


def _expectation_matches(text: str, expectation: dict[str, Any]) -> bool:
    matches = [_concept_matches(text, term) for term in expectation["terms"]]
    return all(matches) if expectation.get("match") == "all" else any(matches)


def _concept_matches(text: str, concept: str) -> bool:
    normalized_text = _normalize_for_match(text)
    normalized_concept = _normalize_for_match(concept)
    if not normalized_concept:
        return False
    if normalized_concept in normalized_text:
        return True

    tokens = _significant_tokens(concept)
    if not tokens:
        return False
    text_tokens = _significant_tokens(text)
    matched = 0
    for token in tokens:
        if any(token in candidate or candidate in token for candidate in text_tokens):
            matched += 1
    required = 1 if len(tokens) == 1 else max(2, math.ceil(len(tokens) * 0.5))
    return matched >= required


def _significant_tokens(value: Any) -> list[str]:
    tokens = re.findall(r"[0-9A-Za-z가-힣]+", str(value or "").casefold())
    normalized: list[str] = []
    for token in tokens:
        token = _strip_korean_suffix(token)
        if len(token) >= 2 and token not in _TOKEN_STOP_WORDS and token not in normalized:
            normalized.append(token)
    return normalized


def _strip_korean_suffix(token: str) -> str:
    for suffix in (
        "입니다",
        "합니다",
        "했습니다",
        "됩니다",
        "있습니다",
        "없습니다",
        "으로부터",
        "으로",
        "에서",
        "에게",
        "까지",
        "부터",
        "처럼",
        "보다",
        "이라",
        "라고",
        "하고",
        "이며",
        "에는",
        "에게",
        "으로",
        "으며",
        "어서",
        "하고",
        "운",
        "움",
        "워",
        "고",
        "며",
        "한",
        "함",
        "된",
        "됨",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "와",
        "과",
        "로",
        "도",
        "만",
    ):
        if len(token) > len(suffix) + 1 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _has_positive_match(pattern: re.Pattern[str], text: str) -> bool:
    for match in pattern.finditer(text):
        if not _is_negated(text, match.start(), match.end()):
            return True
    return False


def _has_current_runtime_match(pattern: re.Pattern[str], text: str) -> bool:
    for match in pattern.finditer(text):
        if _is_negated(text, match.start(), match.end()):
            continue
        after = text[match.end() : min(len(text), match.end() + 28)]
        if re.search(r"(?:원하|요청|전환|사용하려|하려면|필요하면)", after):
            continue
        return True
    return False


def _is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 12) : start]
    after = text[end : min(len(text), end + 38)]
    return bool(_NEGATION_PATTERN.search(before) or _NEGATION_PATTERN.search(after))


def _append_numeric_claim(claims: list[dict[str, Any]], path: str, label: str, value: Any) -> None:
    number = _finite_number(value)
    if number is not None:
        claims.append({"path": path, "label": label, "value": _display_number(number)})


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _finite_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _number_key(value: Any) -> float:
    return round(float(value), 6)


def _display_number(value: Any) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else round(number, 6)


def _unique_place_names(values: Iterable[Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            name = _clean_text(value.get("name"))
        else:
            name = _clean_text(value)
        key = _normalize_for_match(name)
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    # Prefer the longest name when one catalog name is a substring of another.
    return sorted(names, key=lambda item: (-len(_normalize_for_match(item)), item))


def _normalize_for_match(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").casefold())


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _difference(after: Any, before: Any) -> float | None:
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return None
    return round(float(after) - float(before), 4)


def _iso_value(value: date | datetime | str | None) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _format_metric(value: Any) -> str:
    return "미측정" if value is None else f"{float(value) * 100:.1f}%"


def _format_signed_metric(value: Any) -> str:
    return "미측정" if value is None else f"{float(value) * 100:+.1f}%p"


def _variant_runtime_row(label: str, variant: dict[str, Any]) -> str:
    answered = variant.get("answered_records", 0)
    total = variant.get("record_count", 0)
    mean = variant.get("mean_latency_ms")
    p95 = variant.get("p95_latency_ms")
    attempts = variant.get("mean_attempts")
    mean_text = "미측정" if mean is None else f"{float(mean):.1f}ms"
    p95_text = "미측정" if p95 is None else f"{float(p95):.1f}ms"
    attempts_text = "미측정" if attempts is None else f"{float(attempts):.2f}회"
    return f"| {label} | {answered}/{total} | {attempts_text} | {mean_text} | {p95_text} |"


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
