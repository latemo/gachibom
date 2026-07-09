"""Controlled no-RAG baseline responses and validation."""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any

from src.recommendation_case_validation import (
    ACCESSIBILITY_FIELD_LABELS,
    CATEGORY_LABELS,
    CASE_POLICIES,
    FAIL,
    PASS,
    WALKING_LEVEL_LABELS,
    WEATHER_SENSITIVITY_LABELS,
    accessibility_failures,
    add_check,
    add_term_checks,
    escape_table,
    first_matching_text,
    format_code_list,
    format_code_set,
)


NO_RAG_METHOD_ID = "controlled_no_rag_generic_jeju_baseline_v1"
NO_RAG_STATUS = "통제기준선_검증됨"


BASELINE_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "recovery_quiet",
        "prompt": "체력 저하가 있어 긴 걷기와 혼잡한 곳을 피하고 싶은 제주 여행 코스를 추천해줘.",
        "raw_response": (
            "제주 대표 명소를 하루에 묶으면 동문재래시장, 성산일출봉, 협재해수욕장, "
            "애월 카페거리를 둘러보는 코스가 좋습니다. 제주 분위기를 다양하게 볼 수 있습니다."
        ),
        "route": [
            {"name": "동문재래시장", "category": "food_market", "walking_level": "medium", "weather_sensitivity": "low"},
            {"name": "성산일출봉", "category": "oreum", "walking_level": "high", "weather_sensitivity": "high"},
            {"name": "협재해수욕장", "category": "sea", "walking_level": "medium", "weather_sensitivity": "high"},
            {"name": "애월 카페거리", "category": "cafe", "walking_level": "low", "weather_sensitivity": "low"},
        ],
    },
    {
        "id": "diet_restricted",
        "prompt": "음식 제한이 있어 식당이나 시장 중심 장소를 빼고 쉬운 제주 코스를 추천해줘.",
        "raw_response": (
            "제주 맛집과 대표 명소를 함께 즐기려면 동문재래시장, 흑돼지거리, "
            "서귀포매일올레시장, 애월 카페거리를 추천합니다."
        ),
        "route": [
            {"name": "동문재래시장", "category": "food_market", "walking_level": "medium", "weather_sensitivity": "low"},
            {"name": "흑돼지거리", "category": "restaurant", "walking_level": "low", "weather_sensitivity": "low"},
            {"name": "서귀포매일올레시장", "category": "food_market", "walking_level": "medium", "weather_sensitivity": "low"},
            {"name": "애월 카페거리", "category": "cafe", "walking_level": "low", "weather_sensitivity": "low"},
        ],
    },
    {
        "id": "wheelchair_access",
        "prompt": "휠체어를 이용하는 사람이 제주에서 갈 만한 대표 코스를 추천해줘.",
        "raw_response": (
            "제주를 처음 방문한다면 성산일출봉, 우도, 동문재래시장, 협재해수욕장을 추천합니다. "
            "모두 유명해서 여행 만족도가 높습니다."
        ),
        "route": [
            {"name": "성산일출봉", "category": "oreum", "walking_level": "high", "weather_sensitivity": "high"},
            {"name": "우도", "category": "sea", "walking_level": "high", "weather_sensitivity": "high"},
            {"name": "동문재래시장", "category": "food_market", "walking_level": "medium", "weather_sensitivity": "low"},
            {"name": "협재해수욕장", "category": "sea", "walking_level": "medium", "weather_sensitivity": "high"},
        ],
    },
    {
        "id": "stroller_family",
        "prompt": "유모차를 쓰는 아이 동반 가족에게 제주 코스를 추천해줘.",
        "raw_response": (
            "아이와 함께 제주를 느끼려면 협재해수욕장, 성산일출봉, 동문재래시장, 우도를 추천합니다. "
            "사진 찍기 좋고 제주 대표 여행지입니다."
        ),
        "route": [
            {"name": "협재해수욕장", "category": "sea", "walking_level": "medium", "weather_sensitivity": "high"},
            {"name": "성산일출봉", "category": "oreum", "walking_level": "high", "weather_sensitivity": "high"},
            {"name": "동문재래시장", "category": "food_market", "walking_level": "medium", "weather_sensitivity": "low"},
            {"name": "우도", "category": "sea", "walking_level": "high", "weather_sensitivity": "high"},
        ],
    },
    {
        "id": "weather_sensitive",
        "prompt": "비와 바람, 더위에 민감한 사람이 제주에서 갈 만한 코스를 추천해줘.",
        "raw_response": (
            "제주다운 풍경을 보려면 협재해수욕장, 성산일출봉, 새별오름, 우도가 좋습니다. "
            "날씨가 좋으면 전망과 바다를 함께 즐길 수 있습니다."
        ),
        "route": [
            {"name": "협재해수욕장", "category": "sea", "walking_level": "medium", "weather_sensitivity": "high"},
            {"name": "성산일출봉", "category": "oreum", "walking_level": "high", "weather_sensitivity": "high"},
            {"name": "새별오름", "category": "oreum", "walking_level": "high", "weather_sensitivity": "high"},
            {"name": "우도", "category": "sea", "walking_level": "high", "weather_sensitivity": "high"},
        ],
    },
)


def build_no_rag_baseline_responses(*, generated_at: date) -> dict[str, Any]:
    policy_index = {policy["id"]: policy for policy in CASE_POLICIES}
    cases = []
    for item in BASELINE_CASES:
        policy = policy_index[item["id"]]
        cases.append(
            {
                "id": item["id"],
                "label": policy["label"],
                "intent": policy["intent"],
                "prompt": item["prompt"],
                "raw_response": item["raw_response"],
                "extracted": {
                    "score_total": None,
                    "route": [baseline_route_place(place, index + 1) for index, place in enumerate(item["route"])],
                    "fit_reasons": ["제주 대표 명소 위주 추천"],
                    "deduction_reasons": [],
                    "check_before_visit": ["운영 시간 확인"],
                },
            }
        )

    return {
        "generated_at": generated_at.isoformat(),
        "method": {
            "id": NO_RAG_METHOD_ID,
            "type": "controlled_baseline_fixture",
            "rag_used": False,
            "status": NO_RAG_STATUS,
            "note": (
                "실제 외부 모델 호출 로그가 아니라, 근거 저장소 없이 일반 제주 대표 관광지 중심으로 "
                "응답했을 때의 위험을 검증하기 위한 통제 기준선 자료다."
            ),
        },
        "cases": cases,
    }


def baseline_route_place(place: dict[str, Any], order: int) -> dict[str, Any]:
    return {
        "order": order,
        "name": place["name"],
        "category": place["category"],
        "effort": {
            "walking_level": place["walking_level"],
            "weather_sensitivity": place["weather_sensitivity"],
        },
        "accessibility": [
            {"field": "wheelchair_access", "state": "unknown"},
            {"field": "accessible_toilet", "state": "unknown"},
            {"field": "parking", "state": "unknown"},
            {"field": "rest_area", "state": "unknown"},
        ],
        "verification_status": "ungrounded",
        "source_summary": [],
        "blocked": None,
    }


def build_no_rag_baseline_validation_report(
    baseline_responses: dict[str, Any],
    *,
    generated_at: date,
) -> dict[str, Any]:
    policy_index = {policy["id"]: policy for policy in CASE_POLICIES}
    cases = [
        build_no_rag_case_validation(case, policy_index[case["id"]])
        for case in baseline_responses.get("cases", [])
    ]
    passed_cases = sum(1 for case in cases if case["status"] == PASS)
    failed_cases = len(cases) - passed_cases
    passed_checks = sum(case["validation"]["passed_checks"] for case in cases)
    total_checks = sum(case["validation"]["total_checks"] for case in cases)

    return {
        "generated_at": generated_at.isoformat(),
        "method": baseline_responses.get("method", {}),
        "summary": {
            "total_cases": len(cases),
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "overall_status": PASS if failed_cases == 0 else FAIL,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "check_pass_rate": round(passed_checks / total_checks, 4) if total_checks else None,
        },
        "cases": cases,
    }


def build_no_rag_case_validation(case: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    extracted = case.get("extracted", {})
    selected_places = extracted.get("route", [])
    recommendation = {
        "score": {"total": extracted.get("score_total"), "grade": None, "confidence": "ungrounded"},
        "fit_reasons": extracted.get("fit_reasons", []),
        "deduction_reasons": extracted.get("deduction_reasons", []),
        "check_before_visit": extracted.get("check_before_visit", []),
    }
    checks = no_rag_validation_checks(policy, recommendation, selected_places)
    failed_checks = sum(1 for check in checks if check["status"] == FAIL)
    passed_checks = len(checks) - failed_checks

    return {
        "id": case["id"],
        "label": case["label"],
        "intent": case["intent"],
        "status": PASS if failed_checks == 0 else FAIL,
        "prompt": case.get("prompt", ""),
        "raw_response": case.get("raw_response", ""),
        "expected_policy": {
            "recommendation_direction": policy["recommendation_direction"],
            "minimum_total_score": policy.get("min_total_score"),
            "selected_exclude_categories": sorted(policy.get("selected_exclude_categories", [])),
            "required_check_terms": sorted(policy.get("required_check_terms", [])),
            "required_fit_terms": sorted(policy.get("required_fit_terms", [])),
            "policy_effect_terms": sorted(policy.get("policy_effect_terms", [])),
        },
        "recommendation": {
            "score": recommendation["score"],
            "route": [no_rag_route_summary(place) for place in selected_places],
            "fit_reasons": recommendation["fit_reasons"],
            "deduction_reasons": recommendation["deduction_reasons"],
            "check_before_visit": recommendation["check_before_visit"],
        },
        "validation": {
            "total_checks": len(checks),
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "checks": checks,
        },
    }


def no_rag_validation_checks(
    policy: dict[str, Any],
    recommendation: dict[str, Any],
    selected_places: list[dict[str, Any]],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    route_names = [place.get("name", "") for place in selected_places]
    categories = [place.get("category", "other") for place in selected_places]
    walking_levels = [place.get("effort", {}).get("walking_level", "unknown") for place in selected_places]
    weather_levels = [place.get("effort", {}).get("weather_sensitivity", "unknown") for place in selected_places]
    score_total = recommendation.get("score", {}).get("total")

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
        isinstance(score_total, int) and score_total >= policy.get("min_total_score", 0),
        f"{policy.get('min_total_score', 0)}점 이상",
        "점수 미제공" if score_total is None else f"{score_total}점",
    )
    add_check(
        checks,
        "추천",
        "추천 장소 차단 여부",
        all(place.get("blocked") is False for place in selected_places),
        "차단 장소가 추천 결과에 없어야 함",
        "차단 여부 미검증",
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

    add_term_checks(checks, "설명", "추천 근거", policy.get("required_fit_terms", set()), recommendation["fit_reasons"])
    add_term_checks(checks, "설명", "방문 전 확인", policy.get("required_check_terms", set()), recommendation["check_before_visit"])
    add_term_checks(checks, "감점/제외", "정책 효과", policy.get("policy_effect_terms", set()), recommendation["deduction_reasons"])
    return checks


def no_rag_route_summary(place: dict[str, Any]) -> dict[str, Any]:
    effort = place.get("effort", {})
    return {
        "order": place.get("order"),
        "name": place.get("name", ""),
        "category": place.get("category", "other"),
        "walking_level": effort.get("walking_level", "unknown"),
        "weather_sensitivity": effort.get("weather_sensitivity", "unknown"),
        "verification_status": place.get("verification_status", "ungrounded"),
    }


def render_no_rag_cases_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    fieldnames = [
        "case_id",
        "label",
        "status",
        "passed_checks",
        "total_checks",
        "failed_checks",
        "route_names",
        "route_categories",
        "failed_check_names",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for case in report.get("cases", []):
        route = case.get("recommendation", {}).get("route", [])
        failed = [check["name"] for check in case.get("validation", {}).get("checks", []) if check["status"] == FAIL]
        writer.writerow(
            {
                "case_id": case.get("id"),
                "label": case.get("label"),
                "status": case.get("status"),
                "passed_checks": case.get("validation", {}).get("passed_checks"),
                "total_checks": case.get("validation", {}).get("total_checks"),
                "failed_checks": case.get("validation", {}).get("failed_checks"),
                "route_names": "; ".join(place.get("name", "") for place in route),
                "route_categories": "; ".join(place.get("category", "") for place in route),
                "failed_check_names": " | ".join(failed),
            }
        )
    return output.getvalue()


def render_no_rag_baseline_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    method = report.get("method", {})
    lines = [
        "# 무RAG 기준선 검증 자료",
        "",
        f"작성일: {report['generated_at']}",
        "",
        "## 자료 성격",
        "",
        f"- 방법: {method.get('id', NO_RAG_METHOD_ID)}",
        f"- 상태: {method.get('status', NO_RAG_STATUS)}",
        f"- 설명: {method.get('note', '')}",
        "",
        "## 요약",
        "",
        f"- 전체 판정: {summary['overall_status']}",
        f"- 검증 케이스: {summary['total_cases']}개",
        f"- 통과: {summary['passed_cases']}개",
        f"- 실패: {summary['failed_cases']}개",
        f"- 체크 통과: {summary['passed_checks']}/{summary['total_checks']}",
        "",
        "## 케이스 요약",
        "",
        "| 상황 | 판정 | 체크 | 무RAG 추천 경로 | 주요 실패 항목 |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for case in report["cases"]:
        route = ", ".join(place["name"] for place in case["recommendation"]["route"])
        failed = [
            f"{check['area']}:{check['name']}"
            for check in case["validation"]["checks"]
            if check["status"] == FAIL
        ][:6]
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_table(case["label"]),
                    case["status"],
                    f"{case['validation']['passed_checks']}/{case['validation']['total_checks']}",
                    escape_table(route),
                    escape_table(", ".join(failed)),
                ]
            )
            + " |"
        )

    for case in report["cases"]:
        lines.extend(render_no_rag_case_section(case))

    return "\n".join(lines) + "\n"


def render_no_rag_case_section(case: dict[str, Any]) -> list[str]:
    lines = [
        "",
        f"## {case['label']}",
        "",
        f"- 입력: {case['prompt']}",
        f"- 응답 원문: {case['raw_response']}",
        f"- 판정: {case['status']} ({case['validation']['passed_checks']}/{case['validation']['total_checks']} 통과)",
        "",
        "### 추천 경로",
        "",
        "| 순서 | 장소 | 유형 | 도보 부담 | 날씨 민감도 | 근거 상태 |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for place in case["recommendation"]["route"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(place["order"]),
                    escape_table(place["name"]),
                    CATEGORY_LABELS.get(place["category"], place["category"]),
                    WALKING_LEVEL_LABELS.get(place["walking_level"], place["walking_level"]),
                    WEATHER_SENSITIVITY_LABELS.get(place["weather_sensitivity"], place["weather_sensitivity"]),
                    place["verification_status"],
                ]
            )
            + " |"
        )
    lines.extend(["", "### 검증 항목", "", "| 영역 | 항목 | 판정 | 기준 | 실제 |", "| --- | --- | --- | --- | --- |"])
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
    return lines
