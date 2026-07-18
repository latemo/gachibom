"""Build deterministic explanation-quality evaluation cases from the app seed."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.help_chatbot_service import normalize_help_recommendation_context


SCHEMA_VERSION = "1.0"
QUESTION_TYPES: tuple[str, ...] = (
    "recommendation_reason",
    "score_calculation",
    "deduction_reason",
    "pre_visit_check",
    "exclusion_or_alternative",
    "mode_distinction",
)

CONDITION_ALIASES: dict[str, tuple[str, ...]] = {
    "긴 걷기 어려움": ("긴 도보 회피", "장거리 보행", "도보 부담"),
    "체력 저하": ("회복 중", "체력 부담", "낮은 체력"),
    "짧은 이동": ("짧은 동선", "도보 부담이 낮", "이동 거리"),
    "휴식 필요": ("휴식 공간", "중간 휴식", "쉬어"),
    "경사와 계단 확인": ("경사", "계단", "단차"),
    "계단 회피": ("계단", "경사", "단차"),
    "비": ("우천", "날씨"),
    "바람": ("강풍", "날씨"),
    "더위": ("고온", "날씨", "실내"),
    "장시간 야외 체류": ("야외 회피", "야외 노출", "실내 중심"),
    "강풍": ("바람", "날씨"),
    "혼잡": ("대기줄", "사람이 몰", "붐비"),
    "식당 제외": ("식사 장소 제외", "음식 중심 장소 제외", "식당을 제외"),
    "외부 음식 제한": ("음식 제한", "개별 식사", "식사 준비"),
    "정보 부족": ("확인 필요", "정보가 부족"),
    "좁은 길": ("좁은 통로", "통로 폭"),
    "비포장": ("포장 여부", "노면", "바닥"),
    "장애인 화장실": ("화장실",),
    "화장실": ("장애인 화장실",),
    "주차": ("주차장",),
    "휠체어 접근": ("휠체어 동선", "경사로"),
    "휴식 공간": ("휴식", "의자"),
}


def build_explanation_eval_cases(seed: dict[str, Any]) -> dict[str, Any]:
    """Return six fixed explanation questions for every scenario in *seed*."""

    if not isinstance(seed, dict):
        raise ValueError("recommendation seed must be an object")
    scenarios = seed.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("recommendation seed must contain at least one scenario")

    scenario_ids: set[str] = set()
    for scenario in scenarios:
        scenario_id = str(scenario.get("id") or "") if isinstance(scenario, dict) else ""
        if not scenario_id:
            raise ValueError("every scenario must have a non-empty id")
        if scenario_id in scenario_ids:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        scenario_ids.add(scenario_id)

    known_place_names = _unique_strings(
        place.get("name")
        for scenario in scenarios
        if isinstance(scenario, dict)
        for place in scenario.get("places", [])
        if isinstance(place, dict)
    )
    generated_at = str(seed.get("generated_at") or "")
    cases = [
        _build_case(
            scenario,
            question_type,
            generated_at=generated_at,
            known_place_names=known_place_names,
        )
        for scenario in scenarios
        for question_type in QUESTION_TYPES
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_seed": "web/data/app_recommendation_seed.json",
        "generated_at": generated_at,
        "scenario_count": len(scenarios),
        "questions_per_scenario": len(QUESTION_TYPES),
        "case_count": len(cases),
        "cases": cases,
    }


def _build_case(
    scenario: dict[str, Any],
    question_type: str,
    *,
    generated_at: str,
    known_place_names: list[str],
) -> dict[str, Any]:
    scenario_id = str(scenario.get("id") or "")
    places = scenario.get("places")
    if not isinstance(places, list) or not places:
        raise ValueError(f"scenario {scenario_id!r} must contain at least one place")
    if not all(isinstance(place, dict) for place in places):
        raise ValueError(f"scenario {scenario_id!r} contains an invalid place")

    selected_place = _select_place(places, question_type)
    context = _build_recommendation_context(scenario, selected_place, generated_at=generated_at)
    if not context:
        raise ValueError(f"scenario {scenario_id!r} produced an invalid recommendation context")

    selected_context = context.get("selected_place", {})
    recommendation_context = context.get("recommendation", {})
    traveler_summary = context.get("traveler_summary", {})
    selected_name = str(selected_context.get("name") or "")
    selected_id = str(selected_context.get("spot_id") or "")
    selected_score = deepcopy(selected_context.get("score") or {})
    calculation_trace = deepcopy(selected_score.get("calculation_trace") or {})
    route_names = _course_place_names(recommendation_context, places)
    expected = _build_expected(question_type, context=context, route_names=route_names)

    return {
        "id": f"{scenario_id}__{question_type}",
        "scenario_id": scenario_id,
        "scenario_title": str(scenario.get("title") or ""),
        "question_type": question_type,
        "question": _question_text(question_type, selected_name, selected_score, expected),
        "selected_place_id": selected_id,
        "selected_place_name": selected_name,
        "selected_spot": {"spot_id": selected_id, "name": selected_name},
        "recommendation_context": context,
        "expected": expected,
        "expected_mode": expected["mode"],
        "expected_score": selected_score.get("total"),
        "calculation_trace": calculation_trace,
        "expected_evidence": _expected_evidence(question_type, expected),
        "expected_user_conditions": _expected_user_conditions(
            question_type,
            traveler_summary,
            expected=expected,
        ),
        "known_place_names": deepcopy(known_place_names),
        "supported_place_names": deepcopy(route_names),
    }


def _select_place(places: list[dict[str, Any]], question_type: str) -> dict[str, Any]:
    if question_type != "deduction_reason":
        return places[0]

    def deduction_weight(index_and_place: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, place = index_and_place
        reasons = place.get("deduction_reasons")
        reason_count = len(reasons) if isinstance(reasons, list) else 0
        trace = (place.get("score") or {}).get("calculation_trace") or {}
        trace_deductions = trace.get("deductions")
        trace_count = len(trace_deductions) if isinstance(trace_deductions, list) else 0
        return reason_count + trace_count, trace_count, -index

    _, selected = max(enumerate(places), key=deduction_weight)
    return selected


def _build_recommendation_context(
    scenario: dict[str, Any], selected_place: dict[str, Any], *, generated_at: str
) -> dict[str, Any]:
    recommendation = scenario.get("recommendation") or {}
    course = recommendation.get("course") or {}
    route = course.get("route") if isinstance(course.get("route"), list) else []
    raw_context = {
        "mode": "static",
        "generated_at": generated_at,
        "engine": scenario.get("engine") or {"scoring": "precomputed_recommendation_seed"},
        "traveler_summary": deepcopy(scenario.get("traveler_summary") or {}),
        "recommendation": {
            "course": {
                "title": course.get("title") or scenario.get("title") or "추천 코스",
                "summary": course.get("summary") or "",
                "route": [
                    {
                        "order": item.get("order"),
                        "spot_id": item.get("spot_id"),
                        "name": item.get("name"),
                        "purpose": item.get("purpose"),
                        "stay_tip": item.get("stay_tip"),
                    }
                    for item in route[:4]
                    if isinstance(item, dict)
                ],
            },
            "score": deepcopy(recommendation.get("score") or {}),
            "fit_reasons": _list_slice(recommendation.get("fit_reasons"), 8),
            "deduction_reasons": _list_slice(recommendation.get("deduction_reasons"), 8),
            "check_before_visit": _list_slice(recommendation.get("check_before_visit"), 8),
        },
        "selected_place": {
            "spot_id": selected_place.get("spot_id"),
            "name": selected_place.get("name"),
            "score": deepcopy(selected_place.get("score") or {}),
            "fit_reasons": _list_slice(selected_place.get("fit_reasons"), 8),
            "deduction_reasons": _list_slice(selected_place.get("deduction_reasons"), 8),
            "check_before_visit": _list_slice(selected_place.get("check_before_visit"), 8),
            "source_summary": deepcopy(_list_slice(selected_place.get("source_summary"), 3)),
            "verification_status": selected_place.get("verification_status")
            or (selected_place.get("verification") or {}).get("status")
            or "needs_check",
            "blocked": bool(selected_place.get("blocked")),
            "block_reasons": _list_slice(selected_place.get("block_reasons"), 4),
        },
    }
    return normalize_help_recommendation_context(raw_context)


def _build_expected(
    question_type: str, *, context: dict[str, Any], route_names: list[str]
) -> dict[str, Any]:
    selected = context.get("selected_place", {})
    recommendation = context.get("recommendation", {})
    limitations: list[str] = []
    if question_type == "exclusion_or_alternative":
        limitations.append(
            "추천 문맥에는 실제 제외 후보 목록과 후보별 점수가 없으므로 특정 비추천 장소명을 단정하지 않는다."
        )
    return {
        "mode": "static",
        "score": deepcopy(selected.get("score") or {}),
        "course_score": deepcopy(recommendation.get("score") or {}),
        "conditions": deepcopy(context.get("traveler_summary") or {}),
        "reasons": {
            "fit": deepcopy(selected.get("fit_reasons") or []),
            "deductions": deepcopy(selected.get("deduction_reasons") or []),
            "block_reasons": deepcopy(selected.get("block_reasons") or []),
            "course_fit": deepcopy(recommendation.get("fit_reasons") or []),
            "course_deductions": deepcopy(recommendation.get("deduction_reasons") or []),
        },
        "checks": deepcopy(selected.get("check_before_visit") or []),
        "sources": deepcopy(selected.get("source_summary") or []),
        "allowed_course_place_names": deepcopy(route_names),
        "excluded_place_names": [],
        "exclusion_basis": _exclusion_basis(context),
        "limitations": limitations,
    }


def _question_text(
    question_type: str, place_name: str, score: dict[str, Any], expected: dict[str, Any]
) -> str:
    if question_type == "recommendation_reason":
        return f"선택한 장소 '{place_name}'가 제 조건에 추천된 이유를 입력 조건과 근거를 연결해서 설명해 주세요."
    if question_type == "score_calculation":
        return f"'{place_name}'의 점수는 기본 점수부터 보너스·감점·상한 적용까지 어떻게 계산됐나요?"
    if question_type == "deduction_reason":
        if expected["reasons"]["deductions"]:
            return f"'{place_name}'은 어떤 조건 때문에 감점됐나요? 장소 점수와 코스 전체 감점을 구분해 주세요."
        return f"'{place_name}'은 감점된 부분이 있나요? 없다면 없다고 말하고 코스 전체의 주의 근거와 구분해 주세요."
    if question_type == "pre_visit_check":
        return f"'{place_name}'에 방문하기 전에 제 조건상 무엇을 확인해야 하나요?"
    if question_type == "exclusion_or_alternative":
        return (
            "제 입력 조건 때문에 어떤 유형의 장소가 이 코스의 대안으로 덜 적합할 수 있나요? "
            "현재 추천 코스 안에서 함께 고려할 장소만 알려 주세요."
        )
    if question_type == "mode_distinction":
        return f"지금 표시된 '{place_name}' 추천은 제 입력으로 실시간 계산된 결과인가요, 사전 계산된 결과인가요?"
    raise ValueError(f"unsupported question type: {question_type}")


def _expected_evidence(question_type: str, expected: dict[str, Any]) -> list[Any]:
    reasons = expected["reasons"]
    if question_type == "recommendation_reason":
        return deepcopy((reasons["fit"] or reasons["course_fit"])[:4])
    if question_type == "score_calculation":
        score = expected["score"]
        trace = score.get("calculation_trace") or {}
        evidence: list[Any] = [
            {
                "label": "최종 점수",
                "terms": [
                    f"최종 {score.get('total')}점",
                    f"최종 점수 {score.get('total')}",
                    f"final_total {score.get('total')}",
                    f"합계 {score.get('total')}점",
                ],
                "match": "any",
            },
            {
                "label": "기본 점수",
                "terms": [
                    f"기본 {trace.get('base_total')}점",
                    f"기본 점수 {trace.get('base_total')}",
                    f"base_total {trace.get('base_total')}",
                    f"항목별 점수 합계 {trace.get('base_total')}",
                ],
                "match": "any",
            },
        ]
        adjustments = list(trace.get("bonuses", [])) + list(trace.get("deductions", []))
        evidence.extend(str(item.get("label") or "") for item in adjustments[:2])
        return evidence
    if question_type == "deduction_reason":
        return deepcopy((reasons["deductions"] or reasons["course_deductions"])[:4])
    if question_type == "pre_visit_check":
        return deepcopy(expected["checks"][:4])
    if question_type == "exclusion_or_alternative":
        return [
            {
                "label": "사용자가 피하거나 주의해야 할 조건",
                "terms": deepcopy(expected["exclusion_basis"][:6]),
                "match": "any",
            },
            {
                "label": "현재 추천 코스 안의 대안 장소",
                "terms": deepcopy(expected["allowed_course_place_names"]),
                "match": "any",
            },
        ]
    if question_type == "mode_distinction":
        return ["사전 계산 추천"]
    return []


def _expected_user_conditions(
    question_type: str,
    traveler_summary: dict[str, Any],
    *,
    expected: dict[str, Any],
) -> list[Any]:
    if question_type in {"score_calculation", "mode_distinction"}:
        return []
    if question_type == "deduction_reason":
        evidence = expected["reasons"]["deductions"] or expected["reasons"]["course_deductions"]
        if not evidence:
            return []
        candidates = _unique_strings(
            _list_slice(traveler_summary.get("mobility_conditions"), 8)
            + _list_slice(traveler_summary.get("avoid"), 8)
        )
        relevant = [item for item in candidates if _condition_relevant(item, evidence)]
        return [_condition_expectation(item) for item in relevant[:4]]

    groups = [
        _condition_category_expectation(
            "이동 조건",
            _list_slice(traveler_summary.get("mobility_conditions"), 8),
        ),
        _condition_category_expectation(
            "필수 접근성",
            _list_slice(traveler_summary.get("required_accessibility"), 8),
        ),
        _condition_category_expectation(
            "회피 조건",
            _list_slice(traveler_summary.get("avoid"), 8),
        ),
    ]
    if question_type == "exclusion_or_alternative":
        groups = groups[1:]
    return [group for group in groups if group["terms"]]


def _condition_category_expectation(label: str, values: list[Any]) -> dict[str, Any]:
    terms = _unique_strings(
        alias
        for value in values
        if isinstance(value, str)
        for alias in (value, *CONDITION_ALIASES.get(value, ()))
    )
    return {"label": label, "terms": terms, "match": "any"}


def _condition_expectation(value: str) -> dict[str, Any]:
    return {
        "label": value,
        "terms": [value, *CONDITION_ALIASES.get(value, ())],
        "match": "any",
    }


def _condition_relevant(value: str, evidence: list[Any]) -> bool:
    evidence_text = " ".join(str(item or "") for item in evidence).casefold()
    aliases = (value, *CONDITION_ALIASES.get(value, ()))
    return any(
        token in evidence_text
        for alias in aliases
        for token in str(alias).casefold().replace("·", " ").split()
        if len(token) >= 2
    )


def _exclusion_basis(context: dict[str, Any]) -> list[str]:
    traveler_summary = context.get("traveler_summary", {})
    recommendation = context.get("recommendation", {})
    return _unique_strings(
        list(traveler_summary.get("avoid", [])) + list(recommendation.get("deduction_reasons", []))
    )


def _course_place_names(
    recommendation: dict[str, Any], places: list[dict[str, Any]]
) -> list[str]:
    route = (recommendation.get("course") or {}).get("route") or []
    names = _unique_strings(item.get("name") for item in route if isinstance(item, dict))
    return names or _unique_strings(place.get("name") for place in places)


def _list_slice(value: Any, limit: int) -> list[Any]:
    return list(value[:limit]) if isinstance(value, list) else []


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
