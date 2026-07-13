"""Pure aggregation helpers for blinded explanation-quality reviews.

The module intentionally performs no file or network I/O.  It validates
completed review rows against a deblinding key, maps A/B ratings back to the
Before/After variants, and returns JSON-serializable summaries.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Callable, Iterable


RATING_DIMENSIONS = ("correctness", "understanding", "decision_help")
BINARY_DIMENSIONS = ("previsit_clarity", "hallucination", "safety_issue")
VARIANTS = ("before", "after")
PREVISIT_QUESTION_TYPES = {"previsit_check", "pre_visit_check"}

DEFAULT_REQUIRED_ASSIGNMENT_COUNT = 30
DEFAULT_MIN_REVIEWERS_PER_CASE = 3


class HumanEvaluationValidationError(ValueError):
    """Raised when a completed blind-review row cannot be trusted."""


def build_explanation_human_evaluation_report(
    review_rows: Iterable[dict[str, Any]],
    deblind_key: dict[str, Any],
    automatic_report: dict[str, Any],
    *,
    generated_at: date | datetime | str | None = None,
    required_assignment_count: int = DEFAULT_REQUIRED_ASSIGNMENT_COUNT,
    min_reviewers_per_case: int = DEFAULT_MIN_REVIEWERS_PER_CASE,
    fingerprint_validator: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None,
    row_fingerprint_validator: Callable[[dict[str, Any], dict[str, str]], bool] | None = None,
) -> dict[str, Any]:
    """Validate and aggregate blind reviews into a JSON-ready report.

    ``fingerprint_validator`` is an optional source-level integration hook.  A caller that
    owns the packet fingerprint algorithm can compare the key and automatic
    report without introducing a circular dependency in this pure core module.
    It must return truthy on success; a false result rejects the input.

    Assignment and row ``immutable_fingerprint`` tokens are always compared
    when the key supplies them.  ``row_fingerprint_validator`` additionally
    lets the packet owner recompute that token from each row's immutable
    fields; it receives ``(row, assignment)`` and must return truthy.
    """

    if not isinstance(automatic_report, dict):
        raise HumanEvaluationValidationError("automatic_report must be a dictionary")
    if not _positive_int(required_assignment_count):
        raise HumanEvaluationValidationError("required_assignment_count must be a positive integer")
    if not _positive_int(min_reviewers_per_case):
        raise HumanEvaluationValidationError("min_reviewers_per_case must be a positive integer")
    if fingerprint_validator is not None:
        try:
            fingerprint_ok = fingerprint_validator(deblind_key, automatic_report)
        except Exception as exc:
            raise HumanEvaluationValidationError(f"fingerprint validation failed: {exc}") from exc
        if not fingerprint_ok:
            raise HumanEvaluationValidationError("source fingerprint mismatch")

    assignments = _validate_deblind_key(deblind_key)
    raw_rows = list(review_rows)
    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            raise HumanEvaluationValidationError(f"review row {index + 1} must be a dictionary")

    completed: list[dict[str, Any]] = []
    seen_reviewer_assignments: set[tuple[str, str]] = set()
    for index, row in enumerate(raw_rows):
        _validate_row_integrity(
            row,
            assignments,
            index=index,
            row_fingerprint_validator=row_fingerprint_validator,
        )
        status = _text(row.get("review_status")).casefold()
        if status != "complete":
            continue
        normalized = _validate_completed_row(row, assignments, index=index)
        identity = (normalized["blind_id"], normalized["reviewer_id"].casefold())
        if identity in seen_reviewer_assignments:
            raise HumanEvaluationValidationError(
                f"duplicate completed review for blind_id={normalized['blind_id']!r} "
                f"and reviewer_id={normalized['reviewer_id']!r}"
            )
        seen_reviewer_assignments.add(identity)
        completed.append(normalized)

    coverage = _coverage_summary(
        raw_rows,
        completed,
        assignments,
        required_assignment_count=required_assignment_count,
        min_reviewers_per_case=min_reviewers_per_case,
    )
    human_summary = _aggregate_completed_reviews(completed, assignments)
    automatic_score_trace = _automatic_after_score_trace_accuracy(automatic_report)
    gate = _build_gate(human_summary, coverage, automatic_score_trace)

    return {
        "schema_version": "1.0",
        "generated_at": _iso_value(generated_at),
        "human_review_status": "complete" if coverage["complete"] else "pending",
        "methodology": {
            "blinding": "randomized label-blind, single master assignment",
            "rating_aggregation": (
                "각 case_id×variant의 리뷰어 중앙값을 먼저 계산한 뒤 케이스 간 평균"
            ),
            "preference_aggregation": (
                "케이스별 A/B/tie 다수결을 Before/After/tie로 복원한 뒤 non-tie 승률 계산"
            ),
            "previsit_scope": "pre_visit_check 또는 previsit_check 질문에만 적용",
            "minimum_reviewers_per_case": min_reviewers_per_case,
            "limitations": [
                "모든 리뷰어가 같은 master A/B 배치를 사용하므로 케이스별 위치 편향은 완전히 상쇄되지 않음",
                "리뷰어에게 원본 results, 기존 비블라인드 CSV 또는 deblind key를 제공하면 블라인드가 해제될 수 있음",
            ],
        },
        "source": {
            "source_fingerprint": deblind_key.get("source_fingerprint"),
            "fingerprint_validation": "passed" if fingerprint_validator is not None else "not_requested",
            "row_fingerprint_validation": (
                "recomputed"
                if row_fingerprint_validator is not None
                else (
                    "token_match"
                    if any(item.get("immutable_fingerprint") for item in assignments.values())
                    else "not_requested"
                )
            ),
        },
        "coverage": coverage,
        "summary": human_summary,
        "automatic_metrics": {
            "after_score_trace_numeric_accuracy": automatic_score_trace,
        },
        "gate": gate,
    }


def render_explanation_human_evaluation_markdown(report: dict[str, Any]) -> str:
    """Render a compact Korean Markdown summary of a human-review report."""

    coverage = report.get("coverage", {})
    summary = report.get("summary", {})
    variants = summary.get("variants", {})
    deltas = summary.get("deltas", {})
    preference = summary.get("preference", {})
    inter_rater = summary.get("inter_rater", {})
    gate = report.get("gate", {})

    lines = [
        "# 설명 품질 블라인드 사람 평가",
        "",
        f"생성일: {report.get('generated_at') or '미지정'}",
        "",
        f"사람 검토 상태: **{report.get('human_review_status', 'pending')}**",
        f"게이트 상태: **{gate.get('status', 'pending')}**",
        "",
        "> A/B 라벨은 무작위로 숨겼지만 모든 리뷰어가 동일한 master 배치를 사용합니다. 원본 결과와 deblind key는 리뷰 종료 전 공유하지 않습니다.",
        "",
        "## 검토 커버리지",
        "",
        "| 항목 | 결과 |",
        "| --- | ---: |",
        f"| 요구 assignment | {coverage.get('required_assignment_count', 0)} |",
        f"| 실제 assignment | {coverage.get('assignment_count', 0)} |",
        f"| 완료 리뷰 | {coverage.get('completed_review_count', 0)} |",
        f"| 최소 리뷰어 충족 케이스 | {coverage.get('cases_meeting_min_reviewers', 0)}/{coverage.get('assignment_count', 0)} |",
        f"| 케이스당 최소 리뷰어 | {coverage.get('min_reviewers_per_case', 0)}명 |",
        "",
        "## Before/After 사람 평가",
        "",
        "| Variant | 정확성 | 이해도 | 의사결정 도움 | 방문 전 확인 명확 | 환각 이슈 | 안전 이슈 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant, label in (("before", "Before"), ("after", "After")):
        value = variants.get(variant, {})
        ratings = value.get("ratings", {})
        rates = value.get("rates", {})
        lines.append(
            f"| {label} | {_format_rating(ratings.get('correctness'))} | "
            f"{_format_rating(ratings.get('understanding'))} | "
            f"{_format_rating(ratings.get('decision_help'))} | "
            f"{_format_rate(rates.get('previsit_clarity_yes_rate'))} | "
            f"{_format_rate(rates.get('hallucination_yes_rate'))} | "
            f"{_format_rate(rates.get('safety_issue_yes_rate'))} |"
        )

    lines.extend(
        [
            "",
            "## 케이스 균등 가중 결과",
            "",
            f"- After non-tie 선호 승률: {_format_rate(preference.get('after_non_tie_win_rate'))}",
            f"- 케이스 tie 비율: {_format_rate(preference.get('tie_rate'))}",
            f"- 정확성 변화: {_format_signed_rating(deltas.get('correctness'))}",
            f"- 이해도 변화: {_format_signed_rating(deltas.get('understanding'))}",
            f"- 의사결정 도움 변화: {_format_signed_rating(deltas.get('decision_help'))}",
            "",
            "## 평가자 간 일치도",
            "",
            f"- 선호도 pairwise exact agreement: {_format_rate(inter_rater.get('preference_exact_agreement'))}",
            f"- 평점 mean absolute difference: {_format_rating(inter_rater.get('rating_mean_absolute_difference', {}).get('overall'))}",
            "",
            "## 권장 게이트",
            "",
            "| 조건 | 관측값 | 기준 | 결과 |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for check in gate.get("checks", []):
        result = check.get("passed")
        result_text = "대기" if result is None else ("통과" if result else "실패")
        lines.append(
            f"| {_escape_table(check.get('label', check.get('id', '')))} | "
            f"{_format_gate_value(check.get('value'), check.get('format'))} | "
            f"{_escape_table(check.get('threshold_text', ''))} | {result_text} |"
        )
    if gate.get("status") == "pending":
        lines.extend(["", "> 커버리지 기준을 충족하기 전에는 성과 게이트를 최종 판정하지 않습니다."])
    return "\n".join(lines).rstrip() + "\n"


def _validate_deblind_key(deblind_key: Any) -> dict[str, dict[str, str]]:
    if not isinstance(deblind_key, dict):
        raise HumanEvaluationValidationError("deblind_key must be a dictionary")
    values = deblind_key.get("assignments")
    if not isinstance(values, list):
        raise HumanEvaluationValidationError("deblind_key.assignments must be a list")

    assignments: dict[str, dict[str, str]] = {}
    case_ids: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise HumanEvaluationValidationError(f"assignment {index + 1} must be a dictionary")
        blind_id = _required_text(item, "blind_id", f"assignment {index + 1}")
        case_id = _required_text(item, "case_id", f"assignment {index + 1}")
        answer_a_variant = _variant(item.get("answer_a_variant"), f"assignment {blind_id} answer_a_variant")
        answer_b_variant = _variant(item.get("answer_b_variant"), f"assignment {blind_id} answer_b_variant")
        if answer_a_variant == answer_b_variant:
            raise HumanEvaluationValidationError(
                f"assignment {blind_id!r} must map A and B to different variants"
            )
        if blind_id in assignments:
            raise HumanEvaluationValidationError(f"duplicate assignment blind_id: {blind_id!r}")
        if case_id in case_ids:
            raise HumanEvaluationValidationError(f"duplicate assignment case_id: {case_id!r}")
        assignments[blind_id] = {
            "blind_id": blind_id,
            "case_id": case_id,
            "answer_a_variant": answer_a_variant,
            "answer_b_variant": answer_b_variant,
        }
        if item.get("immutable_fingerprint") is not None:
            assignments[blind_id]["immutable_fingerprint"] = _required_text(
                item, "immutable_fingerprint", f"assignment {blind_id}"
            )
        case_ids.add(case_id)
    return assignments


def _validate_row_integrity(
    row: dict[str, Any],
    assignments: dict[str, dict[str, str]],
    *,
    index: int,
    row_fingerprint_validator: Callable[[dict[str, Any], dict[str, str]], bool] | None,
) -> None:
    context = f"review row {index + 1}"
    blind_id = _required_text(row, "blind_id", context)
    assignment = assignments.get(blind_id)
    if assignment is None:
        raise HumanEvaluationValidationError(f"{context} has unknown blind_id: {blind_id!r}")
    expected = assignment.get("immutable_fingerprint")
    if expected is not None:
        actual = _required_text(row, "immutable_fingerprint", context)
        if actual != expected:
            raise HumanEvaluationValidationError(
                f"{context} immutable_fingerprint does not match assignment {blind_id!r}"
            )
    if row_fingerprint_validator is not None:
        try:
            valid = row_fingerprint_validator(row, assignment)
        except Exception as exc:
            raise HumanEvaluationValidationError(
                f"{context} immutable fingerprint validation failed: {exc}"
            ) from exc
        if not valid:
            raise HumanEvaluationValidationError(
                f"{context} immutable fingerprint validation failed for {blind_id!r}"
            )


def _validate_completed_row(
    row: dict[str, Any],
    assignments: dict[str, dict[str, str]],
    *,
    index: int,
) -> dict[str, Any]:
    context = f"completed review row {index + 1}"
    blind_id = _required_text(row, "blind_id", context)
    reviewer_id = _required_text(row, "reviewer_id", context)
    assignment = assignments.get(blind_id)
    if assignment is None:
        raise HumanEvaluationValidationError(f"{context} has unknown blind_id: {blind_id!r}")
    row_case_id = _text(row.get("case_id"))
    if row_case_id and row_case_id != assignment["case_id"]:
        raise HumanEvaluationValidationError(
            f"{context} case_id does not match deblind assignment for {blind_id!r}"
        )
    question_type = _required_text(row, "question_type", context).casefold()
    is_previsit = question_type in PREVISIT_QUESTION_TYPES

    positions: dict[str, dict[str, Any]] = {}
    for position in ("a", "b"):
        ratings = {
            dimension: _rating(row.get(f"answer_{position}_{dimension}_1_5"), f"{context} answer {position.upper()} {dimension}")
            for dimension in RATING_DIMENSIONS
        }
        previsit = _previsit_value(
            row.get(f"answer_{position}_previsit_clarity_yes_no"),
            f"{context} answer {position.upper()} previsit_clarity",
            required=is_previsit,
        )
        positions[position] = {
            "ratings": ratings,
            "previsit_clarity": previsit if is_previsit else None,
            "hallucination": _yes_no(
                row.get(f"answer_{position}_hallucination_yes_no"),
                f"{context} answer {position.upper()} hallucination",
            ),
            "safety_issue": _yes_no(
                row.get(f"answer_{position}_safety_issue_yes_no"),
                f"{context} answer {position.upper()} safety_issue",
            ),
        }

    preference_position = _preference(row.get("preference"), f"{context} preference")
    position_variants = {
        "a": assignment["answer_a_variant"],
        "b": assignment["answer_b_variant"],
    }
    by_variant = {position_variants[position]: value for position, value in positions.items()}
    preferred_variant = "tie" if preference_position == "tie" else position_variants[preference_position.casefold()]
    return {
        "blind_id": blind_id,
        "case_id": assignment["case_id"],
        "question_type": question_type,
        "reviewer_id": reviewer_id,
        "preference_position": preference_position,
        "preferred_variant": preferred_variant,
        "variants": by_variant,
    }


def _coverage_summary(
    raw_rows: list[dict[str, Any]],
    completed: list[dict[str, Any]],
    assignments: dict[str, dict[str, str]],
    *,
    required_assignment_count: int,
    min_reviewers_per_case: int,
) -> dict[str, Any]:
    reviewers_by_case: dict[str, set[str]] = defaultdict(set)
    for review in completed:
        reviewers_by_case[review["case_id"]].add(review["reviewer_id"].casefold())
    counts = {item["case_id"]: len(reviewers_by_case[item["case_id"]]) for item in assignments.values()}
    covered = sum(count > 0 for count in counts.values())
    meeting_minimum = sum(count >= min_reviewers_per_case for count in counts.values())
    assignment_count = len(assignments)
    assignment_count_matches = assignment_count == required_assignment_count
    complete = bool(
        assignment_count_matches
        and assignment_count > 0
        and meeting_minimum == assignment_count
    )
    return {
        "input_review_row_count": len(raw_rows),
        "completed_review_count": len(completed),
        "incomplete_review_row_count": len(raw_rows) - len(completed),
        "assignment_count": assignment_count,
        "required_assignment_count": required_assignment_count,
        "assignment_count_matches_requirement": assignment_count_matches,
        "reviewed_assignment_count": covered,
        "assignment_coverage_rate": _ratio(covered, assignment_count),
        "min_reviewers_per_case": min_reviewers_per_case,
        "cases_meeting_min_reviewers": meeting_minimum,
        "min_reviewer_coverage_rate": _ratio(meeting_minimum, assignment_count),
        "reviewer_counts_by_case": counts,
        "complete": complete,
    }


def _aggregate_completed_reviews(
    completed: list[dict[str, Any]],
    assignments: dict[str, dict[str, str]],
) -> dict[str, Any]:
    variants = {
        variant: _aggregate_variant(completed, assignments, variant)
        for variant in VARIANTS
    }
    deltas: dict[str, float | None] = {}
    for dimension in RATING_DIMENSIONS:
        deltas[dimension] = _difference(
            variants["after"]["ratings"].get(dimension),
            variants["before"]["ratings"].get(dimension),
        )
    for dimension in BINARY_DIMENSIONS:
        key = f"{dimension}_yes_rate"
        deltas[key] = _difference(
            variants["after"]["rates"].get(key),
            variants["before"]["rates"].get(key),
        )
    return {
        "variants": variants,
        "deltas": deltas,
        "preference": _aggregate_preferences(completed, assignments),
        "inter_rater": _aggregate_inter_rater(completed, assignments),
    }


def _aggregate_variant(
    completed: list[dict[str, Any]],
    assignments: dict[str, dict[str, str]],
    variant: str,
) -> dict[str, Any]:
    by_case = _reviews_by_case(completed)
    case_ratings: dict[str, dict[str, float]] = {}
    case_rates: dict[str, dict[str, float | None]] = {}
    raw_ratings: dict[str, list[int]] = {dimension: [] for dimension in RATING_DIMENSIONS}
    raw_flags: dict[str, list[bool]] = {dimension: [] for dimension in BINARY_DIMENSIONS}

    for assignment in assignments.values():
        case_id = assignment["case_id"]
        reviews = by_case.get(case_id, [])
        if not reviews:
            continue
        case_ratings[case_id] = {}
        case_rates[case_id] = {}
        for dimension in RATING_DIMENSIONS:
            values = [review["variants"][variant]["ratings"][dimension] for review in reviews]
            raw_ratings[dimension].extend(values)
            case_ratings[case_id][dimension] = round(float(statistics.median(values)), 4)
        for dimension in BINARY_DIMENSIONS:
            values = [
                review["variants"][variant][dimension]
                for review in reviews
                if review["variants"][variant][dimension] is not None
            ]
            raw_flags[dimension].extend(values)
            case_rates[case_id][dimension] = _mean([1.0 if value else 0.0 for value in values])

    ratings = {
        dimension: _mean([values[dimension] for values in case_ratings.values()])
        for dimension in RATING_DIMENSIONS
    }
    rates = {
        f"{dimension}_yes_rate": _mean(
            [
                values[dimension]
                for values in case_rates.values()
                if values[dimension] is not None
            ]
        )
        for dimension in BINARY_DIMENSIONS
    }
    return {
        "review_count": len(completed),
        "case_count": len(case_ratings),
        "reviewer_count": len({review["reviewer_id"].casefold() for review in completed}),
        "ratings": ratings,
        "rates": rates,
        "raw_reviewer_means": {
            "ratings": {dimension: _mean(values) for dimension, values in raw_ratings.items()},
            "rates": {
                f"{dimension}_yes_rate": _mean([1.0 if value else 0.0 for value in values])
                for dimension, values in raw_flags.items()
            },
        },
        "case_medians": case_ratings,
        "case_rates": case_rates,
    }


def _aggregate_preferences(
    completed: list[dict[str, Any]],
    assignments: dict[str, dict[str, str]],
) -> dict[str, Any]:
    by_case = _reviews_by_case(completed)
    decisions: dict[str, str] = {}
    vote_counts: dict[str, dict[str, int]] = {}
    for assignment in assignments.values():
        case_id = assignment["case_id"]
        reviews = by_case.get(case_id, [])
        if not reviews:
            continue
        counts = {choice: sum(review["preferred_variant"] == choice for review in reviews) for choice in (*VARIANTS, "tie")}
        vote_counts[case_id] = counts
        highest = max(counts.values())
        winners = [choice for choice, count in counts.items() if count == highest]
        decisions[case_id] = winners[0] if len(winners) == 1 else "tie"

    result_counts = {choice: sum(value == choice for value in decisions.values()) for choice in (*VARIANTS, "tie")}
    non_tie = result_counts["after"] + result_counts["before"]
    raw_counts = {choice: sum(review["preferred_variant"] == choice for review in completed) for choice in (*VARIANTS, "tie")}
    raw_non_tie = raw_counts["after"] + raw_counts["before"]
    return {
        "reviewed_case_count": len(decisions),
        "case_decisions": decisions,
        "case_vote_counts": vote_counts,
        "case_counts": result_counts,
        "after_non_tie_win_rate": _ratio(result_counts["after"], non_tie),
        "tie_rate": _ratio(result_counts["tie"], len(decisions)),
        "raw_reviewer_votes": {
            "counts": raw_counts,
            "after_non_tie_win_rate": _ratio(raw_counts["after"], raw_non_tie),
            "tie_rate": _ratio(raw_counts["tie"], len(completed)),
        },
    }


def _aggregate_inter_rater(
    completed: list[dict[str, Any]],
    assignments: dict[str, dict[str, str]],
) -> dict[str, Any]:
    by_case = _reviews_by_case(completed)
    case_metrics: dict[str, dict[str, Any]] = {}
    all_agreements: list[bool] = []
    all_differences: dict[str, list[float]] = {dimension: [] for dimension in RATING_DIMENSIONS}

    for assignment in assignments.values():
        case_id = assignment["case_id"]
        reviews = by_case.get(case_id, [])
        pair_count = len(reviews) * (len(reviews) - 1) // 2
        agreements: list[bool] = []
        differences: dict[str, list[float]] = {dimension: [] for dimension in RATING_DIMENSIONS}
        for left_index in range(len(reviews)):
            for right_index in range(left_index + 1, len(reviews)):
                left = reviews[left_index]
                right = reviews[right_index]
                agreements.append(left["preferred_variant"] == right["preferred_variant"])
                for dimension in RATING_DIMENSIONS:
                    for variant in VARIANTS:
                        differences[dimension].append(
                            abs(
                                left["variants"][variant]["ratings"][dimension]
                                - right["variants"][variant]["ratings"][dimension]
                            )
                        )
        all_agreements.extend(agreements)
        for dimension in RATING_DIMENSIONS:
            all_differences[dimension].extend(differences[dimension])
        dimension_mad = {dimension: _mean(values) for dimension, values in differences.items()}
        case_metrics[case_id] = {
            "reviewer_count": len(reviews),
            "reviewer_pair_count": pair_count,
            "preference_exact_agreement": _mean([1.0 if value else 0.0 for value in agreements]),
            "rating_mean_absolute_difference": {
                **dimension_mad,
                "overall": _mean([value for values in differences.values() for value in values]),
            },
        }

    dimension_mad = {dimension: _mean(values) for dimension, values in all_differences.items()}
    return {
        "eligible_case_count": sum(value["reviewer_pair_count"] > 0 for value in case_metrics.values()),
        "reviewer_pair_count": sum(value["reviewer_pair_count"] for value in case_metrics.values()),
        "preference_exact_agreement": _mean([1.0 if value else 0.0 for value in all_agreements]),
        "preference_case_mean_exact_agreement": _mean(
            [
                value["preference_exact_agreement"]
                for value in case_metrics.values()
                if value["preference_exact_agreement"] is not None
            ]
        ),
        "rating_mean_absolute_difference": {
            **dimension_mad,
            "overall": _mean([value for values in all_differences.values() for value in values]),
        },
        "case_metrics": case_metrics,
    }


def _build_gate(
    summary: dict[str, Any],
    coverage: dict[str, Any],
    automatic_score_trace: float | None,
) -> dict[str, Any]:
    after = summary["variants"]["after"]
    values = {
        "complete_coverage": coverage["complete"],
        "after_preference_win_rate": summary["preference"]["after_non_tie_win_rate"],
        "after_correctness": after["ratings"]["correctness"],
        "after_understanding": after["ratings"]["understanding"],
        "decision_help_delta": summary["deltas"]["decision_help"],
        "after_hallucination_issue_rate": after["rates"]["hallucination_yes_rate"],
        "after_safety_issue_rate": after["rates"]["safety_issue_yes_rate"],
        "automatic_after_score_trace_accuracy": automatic_score_trace,
    }
    specifications = [
        ("complete_coverage", "전체 검토 커버리지", True, lambda value: value is True, "충족", "boolean"),
        ("after_preference_win_rate", "After non-tie 선호 승률", 0.70, lambda value: _at_least(value, 0.70), ">= 70%", "rate"),
        ("after_correctness", "After 정확성", 4.0, lambda value: _at_least(value, 4.0), ">= 4.0/5", "rating"),
        ("after_understanding", "After 이해도", 4.0, lambda value: _at_least(value, 4.0), ">= 4.0/5", "rating"),
        ("decision_help_delta", "의사결정 도움 변화", 0.5, lambda value: _at_least(value, 0.5), ">= +0.5", "rating"),
        ("after_hallucination_issue_rate", "After 환각 이슈율", 0.0, lambda value: _equals(value, 0.0), "= 0%", "rate"),
        ("after_safety_issue_rate", "After 안전 이슈율", 0.0, lambda value: _equals(value, 0.0), "= 0%", "rate"),
        ("automatic_after_score_trace_accuracy", "자동 점수 계산 정확성", 1.0, lambda value: _equals(value, 1.0), "= 100%", "rate"),
    ]
    pending = not coverage["complete"]
    checks = []
    for check_id, label, threshold, predicate, threshold_text, value_format in specifications:
        value = values[check_id]
        passed = None if pending and check_id != "complete_coverage" else bool(predicate(value))
        checks.append(
            {
                "id": check_id,
                "label": label,
                "value": value,
                "threshold": threshold,
                "threshold_text": threshold_text,
                "format": value_format,
                "passed": passed,
            }
        )
    if pending:
        status = "pending"
    else:
        status = "passed" if all(check["passed"] for check in checks) else "failed"
    return {
        "status": status,
        "passed": True if status == "passed" else (False if status == "failed" else None),
        "checks": checks,
    }


def _automatic_after_score_trace_accuracy(report: dict[str, Any]) -> float | None:
    value = (
        report.get("summary", {})
        .get("variants", {})
        .get("after", {})
        .get("metrics", {})
        .get("score_trace_numeric_accuracy")
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return round(float(value), 4)


def _reviews_by_case(completed: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in completed:
        result[review["case_id"]].append(review)
    return result


def _rating(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise HumanEvaluationValidationError(f"{field} must be an integer from 1 to 5")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and value.strip() in {"1", "2", "3", "4", "5"}:
        number = int(value.strip())
    else:
        raise HumanEvaluationValidationError(f"{field} must be an integer from 1 to 5")
    if number < 1 or number > 5:
        raise HumanEvaluationValidationError(f"{field} must be an integer from 1 to 5")
    return number


def _yes_no(value: Any, field: str) -> bool:
    normalized = _text(value).casefold()
    if normalized not in {"yes", "no"}:
        raise HumanEvaluationValidationError(f"{field} must be yes or no")
    return normalized == "yes"


def _previsit_value(value: Any, field: str, *, required: bool) -> bool | None:
    normalized = _text(value).casefold()
    if normalized in {"yes", "no"}:
        return normalized == "yes"
    if normalized in {"", "n/a"} and not required:
        return None
    allowed = "yes or no" if required else "yes, no, n/a, or blank"
    raise HumanEvaluationValidationError(f"{field} must be {allowed}")


def _preference(value: Any, field: str) -> str:
    normalized = _text(value).casefold()
    if normalized == "a":
        return "A"
    if normalized == "b":
        return "B"
    if normalized == "tie":
        return "tie"
    raise HumanEvaluationValidationError(f"{field} must be A, B, or tie")


def _variant(value: Any, field: str) -> str:
    normalized = _text(value).casefold()
    if normalized not in VARIANTS:
        raise HumanEvaluationValidationError(f"{field} must be before or after")
    return normalized


def _required_text(row: dict[str, Any], field: str, context: str) -> str:
    value = _text(row.get(field))
    if not value:
        raise HumanEvaluationValidationError(f"{context} requires {field}")
    return value


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mean(values: Iterable[float | int]) -> float | None:
    items = list(values)
    if not items:
        return None
    return round(sum(float(value) for value in items) / len(items), 4)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else round(numerator / denominator, 4)


def _difference(after: Any, before: Any) -> float | None:
    if isinstance(after, bool) or isinstance(before, bool):
        return None
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return None
    return round(float(after) - float(before), 4)


def _at_least(value: Any, threshold: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) >= threshold


def _equals(value: Any, target: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isclose(float(value), target, abs_tol=1e-9)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _iso_value(value: date | datetime | str | None) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return None if value is None else str(value)


def _format_rating(value: Any) -> str:
    return "미측정" if value is None else f"{float(value):.2f}"


def _format_signed_rating(value: Any) -> str:
    return "미측정" if value is None else f"{float(value):+.2f}"


def _format_rate(value: Any) -> str:
    return "미측정" if value is None else f"{float(value) * 100:.1f}%"


def _format_gate_value(value: Any, value_format: Any) -> str:
    if isinstance(value, bool):
        return "충족" if value else "미충족"
    if value_format == "rate":
        return _format_rate(value)
    if value_format == "rating":
        return _format_rating(value)
    return "미측정" if value is None else str(value)


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
