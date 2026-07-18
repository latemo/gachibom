"""Accessibility fit scoring for Jeju Maeum Travel AI.

The score is a decision-support signal, not a guarantee that a user can visit.
It follows docs/jeju_maeum_scoring_policy.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from src.tourism_weak_courses import tourism_weak_course_bonus


SCORE_MAX = {
    "source_trust": 25,
    "mobility_fit": 25,
    "facility_fit": 20,
    "theme_fit": 15,
    "safety_clarity": 15,
}

GRADE_THRESHOLDS = (
    (85, "A"),
    (70, "B"),
    (50, "C"),
    (30, "D"),
    (0, "F"),
)

GRADE_CAP_TOTAL = {
    "needs_check": 84,
    "unavailable": 69,
}

CATEGORY_TERMS = {
    "sea": {"바다", "해변", "해안", "전망", "올레"},
    "forest": {"숲", "산책", "수목", "정원", "휴식", "치유", "폭포"},
    "oreum": {"오름", "산책", "전망", "야외"},
    "indoor": {"실내", "전시", "박물관", "기념관", "문학", "비", "더위", "날씨"},
    "culture": {"문화", "역사", "전시", "유적", "기념", "공연"},
    "cafe": {"카페", "차", "휴식", "실내"},
    "restaurant": {"식당", "식사", "음식", "밥"},
    "food_market": {"시장", "야시장", "음식", "먹거리", "쇼핑"},
    "shopping": {"쇼핑", "시장", "상점"},
    "rest_area": {"휴식", "공원", "산책"},
    "transport": {"교통", "공항", "버스", "터미널"},
    "medical_support": {"병원", "약국", "응급", "지원"},
    "other": {"시장", "쇼핑", "음식"},
}

SITUATION_RULES = (
    {
        "id": "diet_restriction_no_food",
        "trigger_terms": {
            "식당 제외",
            "음식 제한",
            "외부 음식 제한",
            "밥을 못",
            "먹지 못",
            "식사 조심",
            "음식 조심",
            "식이 제한",
            "diet restriction",
        },
        "exclude_categories": {"restaurant", "food_market"},
        "penalize_categories": {"cafe"},
        "penalize_tags": {"food_focused"},
        "check_before_visit": {"식사 장소 제외 여부", "개별 식사 준비 가능 여부"},
        "reason": "음식 제한 조건이 있어 식사 중심 장소를 제외하거나 감점합니다.",
    },
    {
        "id": "crowd_or_infection_sensitive",
        "trigger_terms": {"혼잡", "사람 많은", "사람이 많은", "감염", "면역", "붐비는", "대기줄", "줄 서기"},
        "exclude_categories": set(),
        "penalize_categories": {"food_market", "shopping", "cafe"},
        "penalize_tags": {"crowded_possible"},
        "check_before_visit": {"혼잡 시간대", "대기줄 여부", "주말·성수기 방문 여부"},
        "reason": "혼잡 또는 감염 우려 조건이 있어 사람이 몰릴 수 있는 장소를 감점합니다.",
    },
    {
        "id": "weather_sensitive",
        "trigger_terms": {"비", "바람", "강풍", "더위", "추위", "날씨", "야외 힘듦", "햇빛"},
        "exclude_categories": set(),
        "penalize_categories": {"sea", "oreum"},
        "penalize_tags": {"weather_sensitive", "outdoor"},
        "check_before_visit": {"방문 당일 날씨", "강풍 여부", "그늘과 실내 대피 가능 여부"},
        "reason": "날씨 민감 조건이 있어 야외 노출 장소를 감점합니다.",
    },
    {
        "id": "sensory_sensitive_low_stimulation",
        "trigger_terms": {"소리 민감", "빛 민감", "어두운 곳", "강한 조명", "자극", "멀미", "어지러움"},
        "exclude_categories": set(),
        "penalize_categories": set(),
        "penalize_tags": {"sensory_intense"},
        "check_before_visit": {"조명과 소리 자극", "어두운 전시장 여부", "휴식 가능한 조용한 공간"},
        "reason": "감각 민감 조건이 있어 강한 자극 요소를 확인해야 합니다.",
    },
)

FIELD_LABELS = {
    "wheelchair_access": "휠체어 접근성",
    "accessible_toilet": "장애인 화장실",
    "parking": "주차",
    "slope_or_stairs": "경사/계단",
    "rest_area": "휴식 공간",
    "rental_or_assistance": "휠체어·유아차 대여",
    "surface_condition": "바닥 상태",
    "crowd_level": "혼잡도",
}


@dataclass(frozen=True)
class PlaceScore:
    """Scoring result for a single place card."""

    spot_id: str
    name: str
    total: int
    grade: str
    confidence: str
    breakdown: dict[str, dict[str, Any]]
    calculation_trace: dict[str, Any]
    fit_reasons: list[str]
    deduction_reasons: list[str]
    check_before_visit: list[str]
    source_summary: list[dict[str, str]]
    blocked: bool
    block_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "spot_id": self.spot_id,
            "name": self.name,
            "score": {
                "total": self.total,
                "grade": self.grade,
                "confidence": self.confidence,
                "breakdown": self.breakdown,
                "calculation_trace": self.calculation_trace,
            },
            "fit_reasons": self.fit_reasons,
            "deduction_reasons": self.deduction_reasons,
            "check_before_visit": self.check_before_visit,
            "source_summary": self.source_summary,
            "blocked": self.blocked,
            "block_reasons": self.block_reasons,
        }


def score_place(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    *,
    today: date | None = None,
) -> PlaceScore:
    """Score one accessibility place card against a traveler summary."""

    today = today or date.today()
    fit_reasons: list[str] = []
    deduction_reasons: list[str] = []
    check_before_visit: list[str] = []

    source_score, source_reason = _score_source_trust(place, today, check_before_visit)
    mobility_score, mobility_reason = _score_mobility_fit(
        place, traveler_summary, fit_reasons, deduction_reasons, check_before_visit
    )
    facility_score, facility_reason = _score_facility_fit(
        place, traveler_summary, fit_reasons, deduction_reasons, check_before_visit
    )
    theme_score, theme_reason = _score_theme_fit(place, traveler_summary, fit_reasons)
    safety_score, safety_reason = _score_safety_clarity(place, check_before_visit)

    base_total = source_score + mobility_score + facility_score + theme_score + safety_score
    bonuses: list[dict[str, Any]] = []
    deductions: list[dict[str, Any]] = []
    caps: list[dict[str, Any]] = []

    situation_bonus = _situation_bonuses(
        place, traveler_summary, fit_reasons, bonuses
    )
    tourism_bonus = tourism_weak_course_bonus(
        place, traveler_summary, fit_reasons, check_before_visit
    )
    if tourism_bonus:
        _append_calculation_delta(
            bonuses,
            "tourism_weak_course",
            "제주관광공사 관광약자 추천코스 근거",
            tourism_bonus,
        )

    forced_deduction = _forced_deductions(
        place,
        traveler_summary,
        deduction_reasons,
        check_before_visit,
        deductions,
    )
    before_score_bounds = base_total + situation_bonus + tourism_bonus - forced_deduction
    total = max(0, min(100, before_score_bounds))
    if total != before_score_bounds:
        caps.append(
            {
                "id": "score_bounds",
                "label": "점수 범위(0~100점) 적용",
                "before": before_score_bounds,
                "after": total,
            }
        )

    verification_status = place.get("verification", {}).get("status", "needs_check")
    if verification_status in GRADE_CAP_TOTAL and total > GRADE_CAP_TOTAL[verification_status]:
        before_verification_cap = total
        total = GRADE_CAP_TOTAL[verification_status]
        caps.append(
            {
                "id": "verification_status",
                "label": f"정보 상태 {verification_status} 등급 상한",
                "before": before_verification_cap,
                "after": total,
            }
        )
        deduction_reasons.append(
            f"정보 상태가 {verification_status}라서 등급 상한을 적용했습니다."
        )

    blocked, block_reasons = _blocking_reasons(place, traveler_summary)
    if blocked:
        before_block_cap = total
        total = min(total, 49)
        caps.append(
            {
                "id": "blocked",
                "label": "추천 제외 조건에 따른 점수 상한",
                "before": before_block_cap,
                "after": total,
            }
        )
        deduction_reasons.extend(block_reasons)

    total = int(round(total))
    grade = grade_for_score(total)
    confidence = confidence_for_status(verification_status, forced_deduction, blocked)

    breakdown = {
        "source_trust": {"score": source_score, "max": SCORE_MAX["source_trust"], "reason": source_reason},
        "mobility_fit": {"score": mobility_score, "max": SCORE_MAX["mobility_fit"], "reason": mobility_reason},
        "facility_fit": {"score": facility_score, "max": SCORE_MAX["facility_fit"], "reason": facility_reason},
        "theme_fit": {"score": theme_score, "max": SCORE_MAX["theme_fit"], "reason": theme_reason},
        "safety_clarity": {"score": safety_score, "max": SCORE_MAX["safety_clarity"], "reason": safety_reason},
    }

    return PlaceScore(
        spot_id=place.get("id", ""),
        name=place.get("name", ""),
        total=total,
        grade=grade,
        confidence=confidence,
        breakdown=breakdown,
        calculation_trace={
            "base_total": base_total,
            "bonuses": bonuses,
            "deductions": deductions,
            "caps": caps,
            "final_total": total,
        },
        fit_reasons=_unique(fit_reasons),
        deduction_reasons=_unique(deduction_reasons),
        check_before_visit=_unique(check_before_visit + _missing_field_checks(place)),
        source_summary=_source_summary(place),
        blocked=blocked,
        block_reasons=_unique(block_reasons),
    )


def rank_places(
    places: list[dict[str, Any]],
    traveler_summary: dict[str, list[str]],
    *,
    limit: int | None = None,
    include_blocked: bool = False,
    today: date | None = None,
) -> list[PlaceScore]:
    """Score and sort places by suitability."""

    scored = [score_place(place, traveler_summary, today=today) for place in places]
    if not include_blocked:
        scored = [item for item in scored if not item.blocked]
    scored.sort(key=lambda item: (item.total, _confidence_rank(item.confidence)), reverse=True)
    return scored[:limit] if limit is not None else scored


def build_recommendation_result(
    scores: list[PlaceScore],
    traveler_summary: dict[str, list[str]],
    *,
    safety_notice: str,
    title: str = "무리 없는 제주 접근성 확인 코스",
) -> dict[str, Any]:
    """Build a recommendation_result.schema.json-compatible object."""

    selected = scores[:4]
    if not selected:
        return {
            "traveler_summary": _traveler_summary_for_schema(traveler_summary),
            "course": {
                "title": title,
                "summary": "조건에 맞는 장소를 찾지 못했습니다.",
                "pace": "unknown",
                "route": [
                    {
                        "order": 1,
                        "spot_id": "no_recommendation",
                        "name": "추천 보류",
                        "purpose": "조건에 맞는 장소 없음",
                        "stay_tip": "공식 정보와 현장 문의를 다시 확인해 주세요.",
                    }
                ],
            },
            "score": _empty_score(),
            "recommended_spots": [],
            "fit_reasons": [],
            "deduction_reasons": ["조건에 맞는 장소가 없어 무리한 추천을 하지 않았습니다."],
            "check_before_visit": ["공식 정보와 현장 문의를 다시 확인해 주세요."],
            "source_summary": [],
            "safety_notice": safety_notice,
        }

    total = int(round(sum(item.total for item in selected) / len(selected)))
    grade = grade_for_score(total)
    confidence = _lowest_confidence([item.confidence for item in selected])
    return {
        "traveler_summary": _traveler_summary_for_schema(traveler_summary),
        "course": {
            "title": title,
            "summary": "선택한 이동 조건에 맞춰 점수가 높은 장소를 짧은 코스로 묶었습니다.",
            "pace": _pace_for_scores(selected),
            "route": [
                {
                    "order": index + 1,
                    "spot_id": item.spot_id,
                    "name": item.name,
                    "purpose": _first_or_default(item.fit_reasons, "접근성 조건 확인"),
                    "stay_tip": _first_or_default(item.check_before_visit, "방문 전 공식 정보 확인"),
                }
                for index, item in enumerate(selected)
            ],
        },
        "score": {
            "total": total,
            "grade": grade,
            "confidence": confidence,
            "breakdown": _average_breakdown(selected),
        },
        "recommended_spots": [item.name for item in selected],
        "fit_reasons": _unique(reason for item in selected for reason in item.fit_reasons),
        "deduction_reasons": _unique(reason for item in selected for reason in item.deduction_reasons),
        "check_before_visit": _unique(item for score in selected for item in score.check_before_visit),
        "source_summary": _unique_sources(item for score in selected for item in score.source_summary),
        "safety_notice": safety_notice,
    }


def grade_for_score(score: int) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def confidence_for_status(status: str, forced_deduction: int, blocked: bool) -> str:
    if blocked or status in {"needs_check", "unavailable"} or forced_deduction >= 25:
        return "low"
    if status == "partial" or forced_deduction:
        return "medium"
    return "high"


def _score_source_trust(
    place: dict[str, Any], today: date, check_before_visit: list[str]
) -> tuple[int, str]:
    verification = place.get("verification", {})
    status = verification.get("status", "needs_check")
    base = {"verified": 22, "partial": 17, "needs_check": 12, "unavailable": 5}.get(status, 8)

    sources = place.get("sources", [])
    has_url = any(source.get("url") for source in sources)
    if has_url:
        base += 3
    else:
        check_before_visit.append("출처 URL을 확인해 주세요.")

    checked_at = verification.get("checked_at")
    freshness_penalty = _freshness_penalty(checked_at, today)
    if freshness_penalty:
        check_before_visit.append("정보 확인일이 오래되었거나 없어 최신 운영 상태를 확인해 주세요.")

    score = max(0, min(SCORE_MAX["source_trust"], base - freshness_penalty))
    return score, f"정보 상태 {status}, 출처 {'있음' if has_url else '없음'} 기준"


def _score_mobility_fit(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    fit_reasons: list[str],
    deduction_reasons: list[str],
    check_before_visit: list[str],
) -> tuple[int, str]:
    effort = place.get("effort", {})
    walking = effort.get("walking_level", "unknown")
    score = {"very_low": 25, "low": 23, "medium": 17, "high": 8, "unknown": 14}.get(walking, 14)

    if _needs_short_walking(traveler_summary):
        if walking in {"very_low", "low"}:
            fit_reasons.append("도보 부담이 낮은 편으로 사용자의 이동 조건과 맞습니다.")
        elif walking == "medium":
            score -= 5
            deduction_reasons.append("도보 부담이 중간 수준이라 짧은 구간 중심으로 확인이 필요합니다.")
        elif walking == "high":
            score -= 12
            deduction_reasons.append("도보 부담이 높아 긴 걷기가 어려운 사용자에게 부담이 큽니다.")

    slope = _field(place, "slope_or_stairs")
    surface = _field(place, "surface_condition")
    if _is_wheelchair_or_stroller(traveler_summary):
        if slope["state"] in {"yes", "partial"}:
            score -= 5
            deduction_reasons.append("경사·계단 또는 단차 요소가 있어 보호자 확인이 필요합니다.")
            check_before_visit.append("경사로, 계단, 단차 상태")
        elif slope["state"] in {"unknown", "needs_check"}:
            score -= 8
            deduction_reasons.append("경사·계단 정보가 부족합니다.")
            check_before_visit.append("경사로, 계단, 단차 상태")

        if surface["state"] in {"partial", "needs_check", "unknown"}:
            score -= 3
            check_before_visit.append("바닥 재질과 요철 여부")

    if _is_recovery_or_low_energy(traveler_summary) and effort.get("outdoor_exposure") == "high":
        score -= 6
        deduction_reasons.append("야외 체류 부담이 높아 체력 저하 사용자에게는 짧은 방문이 필요합니다.")
        check_before_visit.append("날씨, 바람, 그늘, 중간 휴식 가능 여부")

    if _avoids_weather(traveler_summary) and effort.get("weather_sensitivity") in {"medium", "high"}:
        score -= 4
        deduction_reasons.append("날씨 영향을 받을 수 있어 우천·강풍 여부 확인이 필요합니다.")
        check_before_visit.append("방문 당일 날씨와 바람")

    score = max(0, min(SCORE_MAX["mobility_fit"], score))
    return score, f"도보 부담 {walking} 및 경사·바닥 상태 기준"


def _score_facility_fit(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    fit_reasons: list[str],
    deduction_reasons: list[str],
    check_before_visit: list[str],
) -> tuple[int, str]:
    required = _all_terms(traveler_summary.get("required_accessibility", []))
    traveler_terms = _all_terms(traveler_summary.get("traveler_type", []))
    field_weights = {
        "accessible_toilet": 5,
        "parking": 4,
        "rest_area": 4,
        "rental_or_assistance": 3,
        "wheelchair_access": 4,
    }
    score = 0
    missing_requested: list[str] = []

    for field_name, weight in field_weights.items():
        field = _field(place, field_name)
        state = field["state"]
        if state == "yes":
            score += weight
        elif state == "partial":
            score += max(1, weight - 2)
            check_before_visit.append(FIELD_LABELS[field_name])
        elif state in {"needs_check", "unknown"}:
            score += 1
            check_before_visit.append(FIELD_LABELS[field_name])
        else:
            check_before_visit.append(FIELD_LABELS[field_name])

    if _mentions(required, {"화장실", "장애인 화장실", "toilet"}) and _field(place, "accessible_toilet")["state"] != "yes":
        missing_requested.append("요청한 장애인 화장실 정보가 충분하지 않습니다.")
    if _mentions(required, {"주차", "parking"}) and _field(place, "parking")["state"] != "yes":
        missing_requested.append("요청한 주차 정보가 충분하지 않습니다.")
    if _mentions(required | traveler_terms, {"휠체어", "wheelchair"}) and _field(place, "wheelchair_access")["state"] not in {"yes", "partial"}:
        missing_requested.append("휠체어 접근성 정보가 충분하지 않습니다.")

    if missing_requested:
        score -= min(6, len(missing_requested) * 3)
        deduction_reasons.extend(missing_requested)
    else:
        fit_reasons.append("필수 편의시설 정보가 비교적 잘 맞습니다.")

    score = max(0, min(SCORE_MAX["facility_fit"], score))
    return score, "화장실, 주차, 휴식, 대여, 휠체어 접근성 기준"


def _score_theme_fit(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    fit_reasons: list[str],
) -> tuple[int, str]:
    preferred = _all_terms(traveler_summary.get("preferred_themes", []))
    if not preferred:
        return 10, "선호 테마 입력 없음"

    category = place.get("category", "other")
    place_terms = _all_terms([category, place.get("name", ""), place.get("summary", "")])
    category_terms = CATEGORY_TERMS.get(category, set())

    if _mentions(preferred, category_terms | place_terms):
        fit_reasons.append("선호 테마와 장소 성격이 잘 맞습니다.")
        return 15, f"선호 테마와 {category} 카테고리 일치"

    if category in {"indoor", "culture"} and _mentions(preferred, CATEGORY_TERMS["indoor"] | CATEGORY_TERMS["culture"]):
        fit_reasons.append("실내·문화형 선호와 일부 맞습니다.")
        return 12, "실내·문화형 선호와 부분 일치"

    return 6, "선호 테마와 직접 일치하지 않음"


def _score_safety_clarity(
    place: dict[str, Any], check_before_visit: list[str]
) -> tuple[int, str]:
    score = 5
    if place.get("safety_notes"):
        score += 4
    if place.get("avoid_for"):
        score += 2
    missing_fields = place.get("verification", {}).get("missing_fields", [])
    if missing_fields:
        score += 2
        for field in missing_fields:
            check_before_visit.append(FIELD_LABELS.get(field, field))
    if place.get("operator_notes"):
        score += 1
    if place.get("sources"):
        score += 1

    score = max(0, min(SCORE_MAX["safety_clarity"], score))
    return score, "안전 메모, 회피 대상, 확인 필요 항목 기준"


def _forced_deductions(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    deduction_reasons: list[str],
    check_before_visit: list[str],
    calculation_deductions: list[dict[str, Any]] | None = None,
) -> int:
    total = 0
    sources = place.get("sources", [])
    if not any(source.get("url") for source in sources):
        total += 15
        reason = "출처 URL이 없어 강제 감점했습니다."
        deduction_reasons.append(reason)
        _append_calculation_delta(
            calculation_deductions, "missing_source_url", reason, -15
        )

    if not place.get("verification", {}).get("checked_at"):
        total += 10
        reason = "정보 확인일이 없어 강제 감점했습니다."
        deduction_reasons.append(reason)
        _append_calculation_delta(
            calculation_deductions, "missing_verification_date", reason, -10
        )

    required = _all_terms(traveler_summary.get("required_accessibility", []))
    if _mentions(required, {"화장실", "장애인 화장실", "toilet"}) and _field(place, "accessible_toilet")["state"] in {"no", "unknown", "needs_check"}:
        total += 15
        reason = "장애인 화장실을 필수로 요청했지만 정보가 부족합니다."
        deduction_reasons.append(reason)
        _append_calculation_delta(
            calculation_deductions,
            "required_accessible_toilet_missing",
            reason,
            -15,
        )
        check_before_visit.append("장애인 화장실 운영 여부")

    if _mentions(required, {"주차", "가까운 주차", "parking"}) and _field(place, "parking")["state"] in {"no", "unknown", "needs_check"}:
        total += 10
        reason = "가까운 주차를 요청했지만 주차 정보가 부족합니다."
        deduction_reasons.append(reason)
        _append_calculation_delta(
            calculation_deductions, "required_parking_missing", reason, -10
        )
        check_before_visit.append("주차장에서 입구까지 거리")

    if _is_wheelchair_or_stroller(traveler_summary) and _field(place, "slope_or_stairs")["state"] in {"unknown", "needs_check"}:
        total += 20
        reason = "휠체어 또는 유모차 사용자에게 중요한 경사·계단 정보가 부족합니다."
        deduction_reasons.append(reason)
        _append_calculation_delta(
            calculation_deductions, "critical_slope_information_missing", reason, -20
        )

    effort = place.get("effort", {})
    if _needs_short_walking(traveler_summary) and effort.get("walking_level") == "high":
        total += 25
        reason = "긴 걷기가 어려운 조건과 높은 도보 부담이 충돌합니다."
        deduction_reasons.append(reason)
        _append_calculation_delta(
            calculation_deductions, "high_walking_conflict", reason, -25
        )

    if _is_recovery_or_low_energy(traveler_summary) and effort.get("outdoor_exposure") == "high":
        total += 15
        reason = "체력 저하 또는 회복 중 사용자에게 장시간 야외 체류 가능성이 큽니다."
        deduction_reasons.append(reason)
        _append_calculation_delta(
            calculation_deductions, "high_outdoor_exposure", reason, -15
        )

    total += _situation_deductions(
        place,
        traveler_summary,
        deduction_reasons,
        check_before_visit,
        calculation_deductions,
    )

    return total


def _blocking_reasons(
    place: dict[str, Any], traveler_summary: dict[str, list[str]]
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if place.get("status") in {"blocked", "hidden", "deprecated"}:
        reasons.append("운영 상태가 사용자 추천 대상이 아닙니다.")

    verification_status = place.get("verification", {}).get("status")
    if verification_status == "unavailable":
        reasons.append("접근성 판단에 필요한 정보가 거의 없습니다.")

    category = place.get("category", "other")
    for rule in _active_situation_rules(traveler_summary):
        if category in rule["exclude_categories"]:
            reasons.append(f"{rule['reason']} 이 장소 유형은 제외 대상입니다.")

    if _has_strong_avoid_collision(
        traveler_summary.get("avoid", []),
        place.get("avoid_for", []) + place.get("safety_notes", []),
    ):
        reasons.append("사용자가 피하고 싶은 조건과 장소 주의사항이 충돌합니다.")

    if _mentions(_all_terms(traveler_summary.get("preferred_themes", []) + traveler_summary.get("mobility_conditions", [])), {"치료 효과", "회복 효과"}):
        reasons.append("의료적 효과를 이유로 장소를 추천할 수 없습니다.")

    return bool(reasons), reasons


def _field(place: dict[str, Any], field_name: str) -> dict[str, Any]:
    return place.get("accessibility", {}).get(
        field_name, {"state": "unknown", "note": "", "source_ref": None}
    )


def _situation_deductions(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    deduction_reasons: list[str],
    check_before_visit: list[str],
    calculation_deductions: list[dict[str, Any]] | None = None,
) -> int:
    category = place.get("category", "other")
    tags = set(place.get("situation_tags", []))
    total = 0
    for rule in _active_situation_rules(traveler_summary):
        deduction = 0
        if category in rule["penalize_categories"]:
            deduction = 10
        elif tags & rule["penalize_tags"]:
            deduction = 6

        if deduction:
            total += deduction
            deduction_reasons.append(rule["reason"])
            _append_calculation_delta(
                calculation_deductions,
                f"situation_{rule['id']}",
                rule["reason"],
                -deduction,
            )
        check_before_visit.extend(rule["check_before_visit"])
    return total


def _situation_bonuses(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    fit_reasons: list[str],
    calculation_bonuses: list[dict[str, Any]] | None = None,
) -> int:
    terms = _summary_terms(traveler_summary)
    if not _mentions(terms, {"유모차", "stroller", "stroller_family", "아이 동반", "가족"}):
        return 0

    category = place.get("category", "other")
    effort = place.get("effort", {})
    rest_area = _field(place, "rest_area")
    walking = effort.get("walking_level")
    bonus = 0

    if category in {"forest", "rest_area"} and walking in {"very_low", "low"}:
        bonus += 8
        reason = "유모차 가족 조건에 맞는 짧은 휴식형 장소입니다."
        fit_reasons.append(reason)
        _append_calculation_delta(
            calculation_bonuses, "stroller_low_effort_rest", reason, 8
        )
    if category in {"forest", "rest_area"} and rest_area["state"] in {"yes", "partial"}:
        bonus += 4
        reason = "아이와 보호자가 중간에 쉬기 좋은 장소 성격입니다."
        fit_reasons.append(reason)
        _append_calculation_delta(
            calculation_bonuses, "stroller_rest_area", reason, 4
        )

    return bonus


def _active_situation_rules(traveler_summary: dict[str, list[str]]) -> list[dict[str, Any]]:
    terms = _summary_terms(traveler_summary)
    active = []
    for rule in SITUATION_RULES:
        if _mentions(terms, rule["trigger_terms"]):
            active.append(rule)
    return active


def _freshness_penalty(checked_at: str | None, today: date) -> int:
    if not checked_at:
        return 10
    try:
        checked = date.fromisoformat(checked_at)
    except ValueError:
        return 10
    age_days = (today - checked).days
    if age_days > 365:
        return 10
    if age_days > 183:
        return 5
    return 0


def _missing_field_checks(place: dict[str, Any]) -> list[str]:
    return [
        FIELD_LABELS.get(field, field)
        for field in place.get("verification", {}).get("missing_fields", [])
    ]


def _source_summary(place: dict[str, Any]) -> list[dict[str, str]]:
    status = place.get("verification", {}).get("status", "needs_check")
    return [
        {"title": source.get("title", ""), "url": source.get("url", ""), "status": status}
        for source in place.get("sources", [])
    ]


def _traveler_summary_for_schema(traveler_summary: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        "traveler_type": traveler_summary.get("traveler_type", []),
        "mobility_conditions": traveler_summary.get("mobility_conditions", []),
        "preferred_themes": traveler_summary.get("preferred_themes", []),
        "required_accessibility": traveler_summary.get("required_accessibility", []),
        "avoid": traveler_summary.get("avoid", []),
    }


def _empty_score() -> dict[str, Any]:
    empty_item = {"score": 0, "max": 1, "reason": "추천 결과 없음"}
    return {
        "total": 0,
        "grade": "F",
        "confidence": "low",
        "breakdown": {
            "source_trust": empty_item,
            "mobility_fit": empty_item,
            "facility_fit": empty_item,
            "theme_fit": empty_item,
            "safety_clarity": empty_item,
        },
    }


def _average_breakdown(scores: list[PlaceScore]) -> dict[str, dict[str, Any]]:
    return {
        component: {
            "score": int(
                round(
                    sum(score.breakdown[component]["score"] for score in scores)
                    / len(scores)
                )
            ),
            "max": maximum,
            "reason": f"선택 장소 {len(scores)}곳의 항목별 평균",
        }
        for component, maximum in SCORE_MAX.items()
    }


def _pace_for_scores(scores: list[PlaceScore]) -> str:
    if not scores:
        return "unknown"
    average = sum(score.total for score in scores) / len(scores)
    if average >= 80:
        return "slow"
    return "very_slow"


def _lowest_confidence(confidences: list[str]) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return min(confidences, key=lambda value: order.get(value, 0)) if confidences else "low"


def _confidence_rank(confidence: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(confidence, 0)


def _first_or_default(items: list[str], default: str) -> str:
    return items[0] if items else default


def _is_wheelchair_or_stroller(traveler_summary: dict[str, list[str]]) -> bool:
    terms = _summary_terms(traveler_summary)
    return _mentions(terms, {"휠체어", "wheelchair", "유모차", "stroller"})


def _needs_short_walking(traveler_summary: dict[str, list[str]]) -> bool:
    terms = _summary_terms(traveler_summary)
    return _mentions(
        terms,
        {"긴 걷기", "걷기 어려움", "오래 걷기", "짧은 이동", "slow_walker", "체력", "고령", "회복"},
    )


def _is_recovery_or_low_energy(traveler_summary: dict[str, list[str]]) -> bool:
    terms = _summary_terms(traveler_summary)
    return _mentions(terms, {"회복", "항암", "체력", "recovery_traveler", "pregnant", "임신", "고령"})


def _avoids_weather(traveler_summary: dict[str, list[str]]) -> bool:
    terms = _summary_terms(traveler_summary)
    return _mentions(terms, {"비", "바람", "더위", "추위", "날씨", "강풍", "야외"})


def _summary_terms(traveler_summary: dict[str, list[str]]) -> set[str]:
    terms: set[str] = set()
    for value in traveler_summary.values():
        if isinstance(value, list):
            terms.update(_all_terms(value))
    return terms


def _all_terms(values: list[str]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip().lower()
        if not text:
            continue
        terms.add(text)
        for part in text.replace("/", " ").replace(",", " ").split():
            if part:
                terms.add(part)
    return terms


def _mentions(haystack: set[str], needles: set[str]) -> bool:
    for text in haystack:
        for needle in needles:
            if needle and needle.lower() in text:
                return True
    return False


def _has_strong_avoid_collision(user_avoid: list[str], place_warnings: list[str]) -> bool:
    warning_text = " ".join(str(item).lower() for item in place_warnings)
    for phrase in user_avoid:
        text = str(phrase).strip().lower()
        if len(text) < 4:
            continue
        if text in warning_text:
            return True
    return False


def _append_calculation_delta(
    trace: list[dict[str, Any]] | None,
    adjustment_id: str,
    label: str,
    delta: int,
) -> None:
    if trace is not None and delta:
        trace.append({"id": adjustment_id, "label": label, "delta": delta})


def _unique(values: Any) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        key = repr(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _unique_sources(values: Any) -> list[dict[str, str]]:
    seen = set()
    result = []
    for value in values:
        key = value.get("url", "") if isinstance(value, dict) else repr(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
