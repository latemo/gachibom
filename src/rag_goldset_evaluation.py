"""Score approved RAG gold-set runs without inventing missing evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable


SYSTEMS = {"gpt_only", "rule_based", "hybrid"}
DEFAULT_THRESHOLDS = {
    "recall_at_4": 0.90,
    "grounded_claim_rate": 0.95,
    "hard_constraint_violation_rate": 0.0,
    "run_success_rate": 1.0,
}


class GoldsetEvaluationError(ValueError):
    """Raised when an evaluation input cannot be scored safely."""


def build_goldset_evaluation_report(
    goldset: dict[str, Any],
    run_records: Iterable[dict[str, Any]],
    *,
    generated_at: date,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    cases = _goldset_cases(goldset)
    approved_cases = {
        case["id"]: case
        for case in cases
        if case.get("review", {}).get("status") == "approved"
    }
    pending_cases = len(cases) - len(approved_cases)
    effective_thresholds = dict(DEFAULT_THRESHOLDS)
    effective_thresholds.update(thresholds or {})
    records = [_normalize_record(record) for record in run_records]

    if not approved_cases:
        return {
            "schema_version": "1.0",
            "generated_at": generated_at.isoformat(),
            "goldset_id": goldset.get("goldset_id"),
            "status": "blocked_pending_human_review",
            "reportable": False,
            "blockers": [
                "사람이 승인한 골드셋 케이스가 없어 Recall@4와 Grounded Claim Rate를 산출할 수 없습니다."
            ],
            "coverage": {
                "total_cases": len(cases),
                "approved_cases": 0,
                "pending_cases": pending_cases,
                "run_record_count": len(records),
            },
            "thresholds": effective_thresholds,
            "systems": {},
        }

    unknown_case_ids = sorted({record["case_id"] for record in records} - set(approved_cases))
    if unknown_case_ids:
        raise GoldsetEvaluationError(
            "run records reference unapproved or unknown case ids: " + ", ".join(unknown_case_ids[:8])
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["system"]].append(_score_record(record, approved_cases[record["case_id"]]))

    system_reports = {
        system: _aggregate_system(system, scored, approved_cases, effective_thresholds)
        for system, scored in sorted(grouped.items())
    }
    expected_systems = SYSTEMS
    missing_systems = sorted(expected_systems - set(system_reports))
    blockers = []
    if pending_cases:
        blockers.append(f"골드셋 {pending_cases}개 케이스의 사람 승인이 남아 있습니다.")
    if missing_systems:
        blockers.append("실행 결과가 없는 비교 방식: " + ", ".join(missing_systems))

    reportable = pending_cases == 0 and not missing_systems and all(
        item["coverage"]["case_coverage_rate"] == 1.0 for item in system_reports.values()
    )
    return {
        "schema_version": "1.0",
        "generated_at": generated_at.isoformat(),
        "goldset_id": goldset.get("goldset_id"),
        "status": "complete" if reportable else "incomplete",
        "reportable": reportable,
        "blockers": blockers,
        "coverage": {
            "total_cases": len(cases),
            "approved_cases": len(approved_cases),
            "pending_cases": pending_cases,
            "run_record_count": len(records),
        },
        "thresholds": effective_thresholds,
        "systems": system_reports,
    }


def _goldset_cases(goldset: dict[str, Any]) -> list[dict[str, Any]]:
    cases = goldset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise GoldsetEvaluationError("goldset must contain a non-empty cases array")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise GoldsetEvaluationError(f"goldset case #{index} must be an object")
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            raise GoldsetEvaluationError(f"goldset case #{index} is missing id")
        if case_id in seen:
            raise GoldsetEvaluationError(f"duplicate goldset case id: {case_id}")
        seen.add(case_id)
        normalized.append(case)
    return normalized


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise GoldsetEvaluationError("each run record must be an object")
    case_id = str(record.get("case_id") or "").strip()
    system = str(record.get("system") or "").strip()
    if not case_id:
        raise GoldsetEvaluationError("run record is missing case_id")
    if system not in SYSTEMS:
        raise GoldsetEvaluationError(f"unsupported system '{system}' for case '{case_id}'")
    repetition = record.get("repetition", 1)
    if isinstance(repetition, bool) or not isinstance(repetition, int) or repetition < 1:
        raise GoldsetEvaluationError(f"invalid repetition for case '{case_id}'")
    status = str(record.get("status") or "error").strip().casefold()
    ranked_place_ids = record.get("ranked_place_ids") or []
    claims = record.get("claims") or []
    violations = record.get("hard_constraint_violations") or []
    if not isinstance(ranked_place_ids, list) or not all(isinstance(value, str) for value in ranked_place_ids):
        raise GoldsetEvaluationError(f"ranked_place_ids must be a string array for case '{case_id}'")
    if not isinstance(claims, list) or not all(isinstance(value, dict) for value in claims):
        raise GoldsetEvaluationError(f"claims must be an object array for case '{case_id}'")
    if not isinstance(violations, list) or not all(isinstance(value, str) for value in violations):
        raise GoldsetEvaluationError(f"hard_constraint_violations must be a string array for case '{case_id}'")
    return {
        "case_id": case_id,
        "system": system,
        "repetition": repetition,
        "status": status,
        "ranked_place_ids": ranked_place_ids,
        "claims": claims,
        "hard_constraint_violations": violations,
    }


def _score_record(record: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    success = record["status"] == "success"
    expected = case.get("expected", {})
    relevant = set(expected.get("relevant_place_ids") or [])
    top_four = record["ranked_place_ids"][:4]
    allow_no_result = expected.get("allow_no_result") is True
    if not success:
        recall_at_4 = None
        no_result_accuracy = None
    elif relevant:
        recall_at_4 = round(len(relevant & set(top_four)) / len(relevant), 4)
        no_result_accuracy = None
    elif allow_no_result:
        recall_at_4 = None
        no_result_accuracy = 1.0 if not top_four else 0.0
    else:
        recall_at_4 = None
        no_result_accuracy = None

    supported_claims = 0
    scored_claims = 0
    for claim in record["claims"]:
        if isinstance(claim.get("supported"), bool):
            scored_claims += 1
            supported_claims += int(claim["supported"])

    return {
        **record,
        "success": success,
        "recall_at_4": recall_at_4,
        "no_result_accuracy": no_result_accuracy,
        "supported_claims": supported_claims,
        "scored_claims": scored_claims,
        "has_hard_constraint_violation": bool(record["hard_constraint_violations"]),
    }


def _aggregate_system(
    system: str,
    records: list[dict[str, Any]],
    approved_cases: dict[str, dict[str, Any]],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    successful = [record for record in records if record["success"]]
    recall_values = [record["recall_at_4"] for record in successful if record["recall_at_4"] is not None]
    supported_claims = sum(record["supported_claims"] for record in successful)
    scored_claims = sum(record["scored_claims"] for record in successful)
    violating_records = sum(record["has_hard_constraint_violation"] for record in successful)
    covered_case_ids = {record["case_id"] for record in records}
    run_count = len(records)
    success_count = len(successful)
    metrics = {
        "recall_at_4": _mean(recall_values),
        "grounded_claim_rate": _ratio(supported_claims, scored_claims),
        "hard_constraint_violation_rate": _ratio(violating_records, success_count),
        "run_success_rate": _ratio(success_count, run_count),
    }
    checks = {
        metric_id: {
            "value": value,
            "threshold": thresholds[metric_id],
            "passed": _passes(metric_id, value, thresholds[metric_id]),
        }
        for metric_id, value in metrics.items()
    }
    release_ready = all(check["passed"] is True for check in checks.values())
    return {
        "system": system,
        "coverage": {
            "approved_case_count": len(approved_cases),
            "covered_case_count": len(covered_case_ids),
            "case_coverage_rate": _ratio(len(covered_case_ids), len(approved_cases)),
            "run_count": run_count,
            "successful_run_count": success_count,
        },
        "metrics": metrics,
        "metric_checks": checks,
        "claim_counts": {
            "supported": supported_claims,
            "scored": scored_claims,
        },
        "hard_constraint_violation_record_count": violating_records,
        "release_ready": release_ready,
        "records": records,
    }


def _passes(metric_id: str, value: float | None, threshold: float) -> bool | None:
    if value is None:
        return None
    if metric_id == "hard_constraint_violation_rate":
        return value <= threshold
    return value >= threshold


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)
