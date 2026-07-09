"""Build case-by-case validation evidence for recommendation quality."""

from __future__ import annotations

from datetime import date
from typing import Any

from src.app_recommendations import SCENARIOS
from src.recommendation_service import build_runtime_recommendation
from src.scoring import PlaceScore, rank_places


PASS = "통과"
FAIL = "실패"
ACCEPTED_ACCESSIBILITY_STATES = {"yes", "partial"}
CATEGORY_LABELS = {
    "sea": "해안",
    "forest": "숲·산책",
    "oreum": "오름",
    "indoor": "실내",
    "culture": "문화",
    "cafe": "카페",
    "restaurant": "식당",
    "food_market": "먹거리 시장",
    "shopping": "쇼핑",
    "rest_area": "공원·휴식",
    "transport": "교통",
    "medical_support": "의료 지원",
    "other": "기타",
}
WALKING_LEVEL_LABELS = {
    "very_low": "매우 낮음",
    "low": "낮음",
    "medium": "보통",
    "high": "높음",
    "unknown": "정보 부족",
}
WEATHER_SENSITIVITY_LABELS = {
    "low": "낮음",
    "medium": "보통",
    "high": "높음",
    "unknown": "정보 부족",
}
ACCESSIBILITY_FIELD_LABELS = {
    "wheelchair_access": "휠체어 접근",
    "accessible_toilet": "장애인 화장실",
    "parking": "주차",
    "slope_or_stairs": "경사·계단",
    "rest_area": "휴식 공간",
}
ACCESSIBILITY_STATE_LABELS = {
    "yes": "확인됨",
    "partial": "부분 확인",
    "needs_check": "확인 필요",
    "unknown": "정보 부족",
    "no": "해당 없음",
}


CASE_POLICIES: tuple[dict[str, Any], ...] = (
    {
        "id": "recovery_quiet",
        "label": "회복 중",
        "intent": "체력 저하와 긴 걷기 부담을 줄이고, 식사·혼잡·장시간 야외 체류 위험을 피하는 코스",
        "recommendation_direction": "도보 부담이 낮은 실내·문화·휴식 중심 장소를 우선한다.",
        "min_total_score": 85,
        "allowed_walking_levels": {"very_low", "low"},
        "selected_exclude_categories": {"restaurant", "food_market"},
        "required_check_terms": {"휴식", "혼잡", "식사"},
        "required_fit_terms": {"도보 부담", "편의시설"},
        "policy_effect_terms": {"혼잡", "식사"},
    },
    {
        "id": "diet_restricted",
        "label": "음식 제한",
        "intent": "식당·시장처럼 음식 섭취를 전제로 하는 장소를 제외하고, 쉬운 이동과 휴식 중심으로 묶는 코스",
        "recommendation_direction": "식사 중심 장소를 추천에서 배제하고 실내·숲·휴식 장소를 우선한다.",
        "min_total_score": 85,
        "allowed_walking_levels": {"very_low", "low"},
        "selected_exclude_categories": {"restaurant", "food_market"},
        "required_check_terms": {"식사", "개별 식사"},
        "required_fit_terms": {"도보 부담", "편의시설"},
        "policy_effect_terms": {"음식", "식사"},
    },
    {
        "id": "wheelchair_access",
        "label": "휠체어",
        "intent": "휠체어 접근, 장애인 화장실, 주차 정보를 우선 확인하고 경사·계단 변수를 노출하는 코스",
        "recommendation_direction": "휠체어 접근과 필수 편의시설 근거가 있는 장소를 우선한다.",
        "min_total_score": 80,
        "allowed_walking_levels": {"very_low", "low"},
        "required_accessibility_fields": {"wheelchair_access", "accessible_toilet", "parking"},
        "required_check_terms": {"경사", "바닥", "주차"},
        "required_fit_terms": {"도보 부담", "편의시설"},
        "policy_effect_terms": {"경사"},
    },
    {
        "id": "stroller_family",
        "label": "아이 동반",
        "intent": "아이와 보호자가 쉬어갈 수 있고 계단·비포장 부담을 줄이는 짧은 코스",
        "recommendation_direction": "실내 장소만 반복하지 않고 짧은 숲길·공원형 휴식 장소를 포함한다.",
        "min_total_score": 80,
        "allowed_walking_levels": {"very_low", "low"},
        "require_any_category": {"forest", "rest_area"},
        "required_accessibility_fields": {"accessible_toilet", "parking", "rest_area"},
        "required_check_terms": {"경사", "바닥", "휴식"},
        "required_fit_terms": {"유모차", "아이"},
        "policy_effect_terms": {"경사", "날씨"},
    },
    {
        "id": "weather_sensitive",
        "label": "날씨 민감",
        "intent": "비·바람·더위 영향을 줄이고 실내 대피 가능성이 높은 장소를 우선하는 코스",
        "recommendation_direction": "날씨 영향이 큰 바다·오름·고노출 야외 장소를 상위 추천에서 배제한다.",
        "min_total_score": 85,
        "allowed_walking_levels": {"very_low", "low"},
        "allowed_weather_sensitivity": {"low", "medium"},
        "selected_exclude_categories": {"sea", "oreum"},
        "required_check_terms": {"날씨", "강풍", "그늘"},
        "required_fit_terms": {"도보 부담", "편의시설"},
        "policy_effect_terms": {"날씨"},
    },
)


def build_recommendation_case_validation_report(
    places: list[dict[str, Any]],
    *,
    generated_at: date,
    limit: int = 4,
) -> dict[str, Any]:
    scenario_index = {scenario["id"]: scenario for scenario in SCENARIOS}
    place_index = {place.get("id", ""): place for place in places}
    cases = [
        build_case_validation(
            scenario_index[policy["id"]],
            policy,
            places,
            place_index,
            generated_at=generated_at,
            limit=limit,
        )
        for policy in CASE_POLICIES
    ]
    passed_cases = sum(1 for case in cases if case["status"] == PASS)
    failed_cases = len(cases) - passed_cases
    return {
        "generated_at": generated_at.isoformat(),
        "source": {
            "places": "data/jeju_accessible_spots.json",
            "scoring_policy": "src/scoring.py",
            "runtime_service": "src/recommendation_service.py",
        },
        "summary": {
            "total_cases": len(cases),
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "overall_status": PASS if failed_cases == 0 else FAIL,
        },
        "cases": cases,
    }


def build_case_validation(
    scenario: dict[str, Any],
    policy: dict[str, Any],
    places: list[dict[str, Any]],
    place_index: dict[str, dict[str, Any]],
    *,
    generated_at: date,
    limit: int,
) -> dict[str, Any]:
    result = build_runtime_recommendation(
        places,
        scenario["traveler_summary"],
        today=generated_at,
        limit=limit,
        use_ai=False,
    )
    all_scores = rank_places(
        places,
        result["traveler_summary"],
        include_blocked=True,
        today=generated_at,
    )
    selected_places = result["places"]
    excluded_candidates = [
        candidate_summary(score, place_index.get(score.spot_id, {}))
        for score in all_scores
        if score.blocked
    ][:10]
    deduction_samples = [
        candidate_summary(score, place_index.get(score.spot_id, {}))
        for score in all_scores
        if score.deduction_reasons and not score.blocked
    ][:10]
    checks = validation_checks(policy, result, selected_places, excluded_candidates, deduction_samples)
    failed_checks = sum(1 for check in checks if check["status"] == FAIL)
    passed_checks = len(checks) - failed_checks

    return {
        "id": policy["id"],
        "label": policy["label"],
        "title": scenario["title"],
        "intent": policy["intent"],
        "status": PASS if failed_checks == 0 else FAIL,
        "traveler_summary": result["traveler_summary"],
        "expected_policy": {
            "recommendation_direction": policy["recommendation_direction"],
            "minimum_total_score": policy.get("min_total_score"),
            "selected_exclude_categories": sorted(policy.get("selected_exclude_categories", [])),
            "required_check_terms": sorted(policy.get("required_check_terms", [])),
            "required_fit_terms": sorted(policy.get("required_fit_terms", [])),
            "policy_effect_terms": sorted(policy.get("policy_effect_terms", [])),
        },
        "recommendation": {
            "score": result["recommendation"]["score"],
            "route": [route_place_summary(place, index + 1) for index, place in enumerate(selected_places)],
            "fit_reasons": result["recommendation"]["fit_reasons"],
            "deduction_reasons": result["recommendation"]["deduction_reasons"],
            "check_before_visit": result["recommendation"]["check_before_visit"],
        },
        "validation": {
            "total_checks": len(checks),
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "checks": checks,
        },
        "excluded_candidates": excluded_candidates,
        "deduction_samples": deduction_samples,
    }


def validation_checks(
    policy: dict[str, Any],
    result: dict[str, Any],
    selected_places: list[dict[str, Any]],
    excluded_candidates: list[dict[str, Any]],
    deduction_samples: list[dict[str, Any]],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    recommendation = result["recommendation"]
    route_names = [place.get("name", "") for place in selected_places]
    categories = [place.get("category", "other") for place in selected_places]
    walking_levels = [place.get("effort", {}).get("walking_level", "unknown") for place in selected_places]
    weather_levels = [
        place.get("effort", {}).get("weather_sensitivity", "unknown")
        for place in selected_places
    ]

    add_check(
        checks,
        "추천",
        "추천 장소 수",
        bool(selected_places),
        "조건에 맞는 추천 장소가 1곳 이상 있어야 함",
        f"{len(selected_places)}곳: {', '.join(route_names)}",
    )
    add_check(
        checks,
        "추천",
        "총점 기준",
        recommendation["score"]["total"] >= policy.get("min_total_score", 0),
        f"{policy.get('min_total_score', 0)}점 이상",
        f"{recommendation['score']['total']}점",
    )
    add_check(
        checks,
        "추천",
        "추천 장소 차단 여부",
        not any(place.get("blocked") for place in selected_places),
        "차단 장소가 추천 결과에 없어야 함",
        "차단 장소 없음" if not any(place.get("blocked") for place in selected_places) else "차단 장소 포함",
    )

    allowed_walking = set(policy.get("allowed_walking_levels", []))
    if allowed_walking:
        add_check(
            checks,
            "추천",
            "도보 부담",
            all(level in allowed_walking for level in walking_levels),
            f"{format_code_set(allowed_walking, WALKING_LEVEL_LABELS)}만 허용",
            format_code_list(walking_levels, WALKING_LEVEL_LABELS),
        )

    required_categories = set(policy.get("require_any_category", []))
    if required_categories:
        add_check(
            checks,
            "추천",
            "필수 장소 성격 포함",
            any(category in required_categories for category in categories),
            f"{format_code_set(required_categories, CATEGORY_LABELS)} 중 1개 이상 포함",
            format_code_list(categories, CATEGORY_LABELS),
        )

    excluded_categories = set(policy.get("selected_exclude_categories", []))
    if excluded_categories:
        add_check(
            checks,
            "제외",
            "상위 추천 제외 유형",
            not any(category in excluded_categories for category in categories),
            f"{format_code_set(excluded_categories, CATEGORY_LABELS)} 미포함",
            format_code_list(categories, CATEGORY_LABELS),
        )

    allowed_weather = set(policy.get("allowed_weather_sensitivity", []))
    if allowed_weather:
        add_check(
            checks,
            "제외",
            "날씨 민감도",
            all(level in allowed_weather for level in weather_levels),
            f"{format_code_set(allowed_weather, WEATHER_SENSITIVITY_LABELS)}만 허용",
            format_code_list(weather_levels, WEATHER_SENSITIVITY_LABELS),
        )

    required_fields = set(policy.get("required_accessibility_fields", []))
    if required_fields:
        failing_places = accessibility_failures(selected_places, required_fields)
        add_check(
            checks,
            "근거",
            "필수 편의시설 상태",
            not failing_places,
            f"{format_code_set(required_fields, ACCESSIBILITY_FIELD_LABELS)}는 확인됨 또는 부분 확인이어야 함",
            "모두 확인 범위" if not failing_places else "; ".join(failing_places),
        )

    text_sources = {
        "fit": recommendation.get("fit_reasons", []),
        "check": recommendation.get("check_before_visit", []),
        "effect": (
            recommendation.get("deduction_reasons", [])
            + flatten_candidate_reasons(excluded_candidates)
            + flatten_candidate_reasons(deduction_samples)
        ),
    }
    add_term_checks(checks, "설명", "추천 근거", policy.get("required_fit_terms", set()), text_sources["fit"])
    add_term_checks(checks, "설명", "방문 전 확인", policy.get("required_check_terms", set()), text_sources["check"])
    add_term_checks(checks, "감점/제외", "정책 효과", policy.get("policy_effect_terms", set()), text_sources["effect"])
    return checks


def add_check(
    checks: list[dict[str, str]],
    area: str,
    name: str,
    passed: bool,
    expected: str,
    actual: str,
) -> None:
    checks.append(
        {
            "area": area,
            "name": name,
            "status": PASS if passed else FAIL,
            "expected": expected,
            "actual": actual,
        }
    )


def add_term_checks(
    checks: list[dict[str, str]],
    area: str,
    name: str,
    terms: set[str],
    values: list[str],
) -> None:
    text = " ".join(values)
    for term in sorted(terms):
        add_check(
            checks,
            area,
            f"{name}: {term}",
            term in text,
            f"{term} 관련 근거가 있어야 함",
            first_matching_text(values, term) or "근거 없음",
        )


def accessibility_failures(places: list[dict[str, Any]], required_fields: set[str]) -> list[str]:
    failures = []
    for place in places:
        state_by_field = {
            item.get("field"): item.get("state", "unknown")
            for item in place.get("accessibility", [])
            if isinstance(item, dict)
        }
        for field in sorted(required_fields):
            state = state_by_field.get(field, "unknown")
            if state not in ACCEPTED_ACCESSIBILITY_STATES:
                failures.append(
                    f"{place.get('name', '')} "
                    f"{ACCESSIBILITY_FIELD_LABELS.get(field, field)}="
                    f"{ACCESSIBILITY_STATE_LABELS.get(state, state)}"
                )
    return failures


def route_place_summary(place: dict[str, Any], order: int) -> dict[str, Any]:
    effort = place.get("effort", {})
    score = place.get("score", {})
    return {
        "order": order,
        "spot_id": place.get("spot_id", ""),
        "name": place.get("name", ""),
        "category": place.get("category", "other"),
        "score_total": score.get("total", 0),
        "walking_level": effort.get("walking_level", "unknown"),
        "weather_sensitivity": effort.get("weather_sensitivity", "unknown"),
        "verification_status": place.get("verification_status", "needs_check"),
    }


def candidate_summary(score: PlaceScore, place: dict[str, Any]) -> dict[str, Any]:
    return {
        "spot_id": score.spot_id,
        "name": score.name,
        "category": place.get("category", "other"),
        "score_total": score.total,
        "blocked": score.blocked,
        "block_reasons": score.block_reasons,
        "deduction_reasons": score.deduction_reasons,
    }


def flatten_candidate_reasons(candidates: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for candidate in candidates:
        reasons.extend(candidate.get("block_reasons", []))
        reasons.extend(candidate.get("deduction_reasons", []))
    return reasons


def first_matching_text(values: list[str], term: str) -> str:
    for value in values:
        if term in value:
            return value
    return ""


def render_recommendation_case_validation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 추천 상황별 검증표",
        "",
        f"작성일: {report['generated_at']}",
        "",
        "## 요약",
        "",
        f"- 전체 판정: {report['summary']['overall_status']}",
        f"- 검증 케이스: {report['summary']['total_cases']}개",
        f"- 통과: {report['summary']['passed_cases']}개",
        f"- 실패: {report['summary']['failed_cases']}개",
        "",
        "## 케이스 요약",
        "",
        "| 상황 | 판정 | 총점 | 추천 장소 | 핵심 기준 |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for case in report["cases"]:
        route = ", ".join(place["name"] for place in case["recommendation"]["route"])
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_table(case["label"]),
                    case["status"],
                    str(case["recommendation"]["score"]["total"]),
                    escape_table(route),
                    escape_table(case["expected_policy"]["recommendation_direction"]),
                ]
            )
            + " |"
        )

    for case in report["cases"]:
        lines.extend(render_case_section(case))

    return "\n".join(lines) + "\n"


def render_case_section(case: dict[str, Any]) -> list[str]:
    lines = [
        "",
        f"## {case['label']}",
        "",
        f"- 의도: {case['intent']}",
        f"- 추천 방향: {case['expected_policy']['recommendation_direction']}",
        f"- 판정: {case['status']} ({case['validation']['passed_checks']}/{case['validation']['total_checks']} 통과)",
        "",
        "### 추천 결과",
        "",
        "| 순서 | 장소 | 유형 | 점수 | 도보 부담 | 날씨 민감도 |",
        "| ---: | --- | --- | ---: | --- | --- |",
    ]
    for place in case["recommendation"]["route"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(place["order"]),
                    escape_table(place["name"]),
                    CATEGORY_LABELS.get(place["category"], place["category"]),
                    str(place["score_total"]),
                    WALKING_LEVEL_LABELS.get(place["walking_level"], place["walking_level"]),
                    WEATHER_SENSITIVITY_LABELS.get(
                        place["weather_sensitivity"],
                        place["weather_sensitivity"],
                    ),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "### 검증 항목",
            "",
            "| 영역 | 항목 | 판정 | 기준 | 실제 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for check in case["validation"]["checks"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_table(check["area"]),
                    escape_table(check["name"]),
                    check["status"],
                    escape_table(check["expected"]),
                    escape_table(check["actual"]),
                ]
            )
            + " |"
        )

    lines.extend(render_reason_list("추천 근거", case["recommendation"]["fit_reasons"]))
    lines.extend(render_reason_list("감점 근거", case["recommendation"]["deduction_reasons"]))
    lines.extend(render_reason_list("방문 전 확인", case["recommendation"]["check_before_visit"]))
    lines.extend(render_candidate_table("제외된 후보 예시", case["excluded_candidates"]))
    lines.extend(render_candidate_table("감점 후보 예시", case["deduction_samples"]))
    return lines


def render_reason_list(title: str, reasons: list[str]) -> list[str]:
    lines = ["", f"### {title}", ""]
    if not reasons:
        lines.append("- 해당 없음")
        return lines
    lines.extend(f"- {reason}" for reason in reasons)
    return lines


def render_candidate_table(title: str, candidates: list[dict[str, Any]]) -> list[str]:
    lines = ["", f"### {title}", ""]
    if not candidates:
        lines.append("- 해당 없음")
        return lines
    lines.extend(
        [
            "| 장소 | 유형 | 점수 | 이유 |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for candidate in candidates[:5]:
        reasons = candidate.get("block_reasons") or candidate.get("deduction_reasons") or ["근거 없음"]
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_table(candidate["name"]),
                    CATEGORY_LABELS.get(candidate["category"], candidate["category"]),
                    str(candidate["score_total"]),
                    escape_table("; ".join(reasons)),
                ]
            )
            + " |"
        )
    return lines


def escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def format_code_set(values: set[str], labels: dict[str, str]) -> str:
    return ", ".join(labels.get(value, value) for value in sorted(values))


def format_code_list(values: list[str], labels: dict[str, str]) -> str:
    return ", ".join(labels.get(value, value) for value in values)
