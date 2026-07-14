"""Build app-facing recommendation seed data."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from src.place_locations import normalize_point_role
from src.place_visit_info import visit_info_for_place
from src.rag_query import parse_query_intent
from src.rag_retrieval import retrieve_place_candidates
from src.route_optimization import optimize_course_route
from src.scoring import PlaceScore, build_recommendation_result, rank_places


SAFETY_NOTICE = (
    "이 서비스는 의료 판단이나 여행 가능성을 보장하지 않습니다. "
    "현장 접근성은 날씨, 운영 상황, 공사, 혼잡도에 따라 달라질 수 있으므로 "
    "방문 전 공식 정보와 현장 문의를 확인해 주세요."
)


SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "id": "recovery_quiet",
        "label": "회복 중",
        "title": "짧고 조용한 회복 여행",
        "traveler_summary": {
            "traveler_type": ["recovery_traveler", "caregiver_group"],
            "mobility_conditions": ["체력 저하", "긴 걷기 어려움", "휴식 필요"],
            "preferred_themes": ["실내", "문화", "휴식"],
            "required_accessibility": ["장애인 화장실", "주차", "휴식 공간"],
            "avoid": ["식당 제외", "혼잡", "장시간 야외 체류"],
        },
    },
    {
        "id": "wheelchair_access",
        "label": "휠체어",
        "title": "휠체어 접근 확인 코스",
        "traveler_summary": {
            "traveler_type": ["wheelchair_user"],
            "mobility_conditions": ["긴 걷기 어려움", "경사와 계단 확인"],
            "preferred_themes": ["실내", "문화"],
            "required_accessibility": ["장애인 화장실", "주차", "휠체어 접근"],
            "avoid": ["계단", "정보 부족"],
        },
    },
    {
        "id": "stroller_family",
        "label": "아이 동반",
        "title": "아이 동반 짧은 코스",
        "traveler_summary": {
            "traveler_type": ["stroller_family"],
            "mobility_conditions": ["계단 회피", "짧은 이동", "휴식 필요"],
            "preferred_themes": ["실내", "공원", "문화"],
            "required_accessibility": ["화장실", "주차", "휴식 공간"],
            "avoid": ["좁은 길", "비포장"],
        },
    },
    {
        "id": "weather_sensitive",
        "label": "날씨 민감",
        "title": "날씨 영향을 줄인 코스",
        "traveler_summary": {
            "traveler_type": ["senior"],
            "mobility_conditions": ["비", "바람", "더위", "짧은 이동"],
            "preferred_themes": ["실내", "문화"],
            "required_accessibility": ["장애인 화장실", "주차"],
            "avoid": ["장시간 야외 체류", "강풍"],
        },
    },
    {
        "id": "diet_restricted",
        "label": "음식 제한",
        "title": "식사 장소를 제외한 코스",
        "traveler_summary": {
            "traveler_type": ["recovery_traveler", "diet_restricted_traveler"],
            "mobility_conditions": ["체력 저하", "짧은 이동"],
            "preferred_themes": ["실내", "휴식", "문화"],
            "required_accessibility": ["장애인 화장실", "주차"],
            "avoid": ["식당 제외", "외부 음식 제한", "혼잡"],
        },
    },
)


SCENARIO_CONDITION_FOCUS: dict[str, tuple[tuple[str, str], ...]] = {
    "recovery_quiet": (
        ("traveler_type", "caregiver_group"),
        ("mobility_conditions", "휴식 필요"),
        ("mobility_conditions", "긴 걷기 어려움"),
        ("preferred_themes", "실내"),
        ("required_accessibility", "주차"),
        ("required_accessibility", "장애인 화장실"),
        ("required_accessibility", "휴식 공간"),
    ),
    "diet_restricted": (
        ("traveler_type", "diet_restricted_traveler"),
        ("mobility_conditions", "체력 저하"),
        ("mobility_conditions", "짧은 이동"),
        ("preferred_themes", "실내"),
        ("required_accessibility", "주차"),
        ("required_accessibility", "장애인 화장실"),
        ("avoid", "식당 제외"),
    ),
    "stroller_family": (
        ("traveler_type", "stroller_family"),
        ("mobility_conditions", "휴식 필요"),
        ("mobility_conditions", "짧은 이동"),
        ("preferred_themes", "공원"),
        ("required_accessibility", "주차"),
        ("required_accessibility", "화장실"),
        ("required_accessibility", "휴식 공간"),
    ),
    "wheelchair_access": (
        ("traveler_type", "wheelchair_user"),
        ("mobility_conditions", "긴 걷기 어려움"),
        ("mobility_conditions", "경사와 계단 확인"),
        ("preferred_themes", "실내"),
        ("required_accessibility", "주차"),
        ("required_accessibility", "장애인 화장실"),
        ("required_accessibility", "휠체어 접근"),
    ),
    "weather_sensitive": (
        ("traveler_type", "senior"),
        ("mobility_conditions", "바람"),
        ("mobility_conditions", "짧은 이동"),
        ("preferred_themes", "실내"),
        ("required_accessibility", "주차"),
        ("required_accessibility", "장애인 화장실"),
        ("avoid", "강풍"),
    ),
}


VISUAL_ASSETS = (
    {"src": "assets/WELCOME-1-001.jpg", "caption": "실내 진입부 확인 이미지"},
    {"src": "assets/JEJUNATIONALMU-1-001.jpg", "caption": "주차장과 출입 방향 확인 이미지"},
    {"src": "assets/SAMSUNGHYEOL-1-001.jpg", "caption": "야외 동선 확인 이미지"},
)


ACCESSIBILITY_FIELDS = (
    "wheelchair_access",
    "accessible_toilet",
    "parking",
    "slope_or_stairs",
    "rest_area",
    "rental_or_assistance",
    "surface_condition",
    "crowd_level",
)


ACCESSIBILITY_FIELD_LABELS = {
    "wheelchair_access": "휠체어 접근",
    "accessible_toilet": "장애인 화장실",
    "parking": "주차",
    "slope_or_stairs": "경사·계단",
    "rest_area": "휴식 공간",
    "rental_or_assistance": "대여·보조",
    "surface_condition": "바닥 상태",
    "crowd_level": "혼잡도",
}


ACCESSIBILITY_STATE_LABELS = {
    "yes": "확인됨",
    "partial": "부분 확인",
    "needs_check": "확인 필요",
    "unknown": "정보 부족",
    "no": "해당 없음",
}


def build_app_recommendation_seed(
    places: list[dict[str, Any]],
    *,
    generated_at: date,
    limit: int = 4,
    location_index: dict[str, dict[str, Any]] | None = None,
    tourism_weak_course_dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    place_index = {place.get("id", ""): place for place in places}
    location_index = location_index or {}
    scenarios = [
        build_app_scenario(
            scenario,
            places,
            place_index,
            generated_at=generated_at,
            limit=limit,
            location_index=location_index,
        )
        for scenario in SCENARIOS
    ]
    return {
        "generated_at": generated_at.isoformat(),
        "safety_notice": SAFETY_NOTICE,
        "public_gate": public_gate_summary(places),
        "saved_route_places": saved_route_place_index(places, location_index=location_index),
        "visual_assets": list(VISUAL_ASSETS),
        "official_courses": official_course_exposure(
            tourism_weak_course_dataset or {},
            place_index,
            location_index=location_index,
        ),
        "scenarios": scenarios,
    }


def saved_route_place_index(
    places: list[dict[str, Any]],
    *,
    location_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the public fields needed to reopen a saved or shared route."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for place in places:
        spot_id = str(place.get("id") or "").strip()
        name = str(place.get("name") or "").strip()
        if not spot_id or not name or spot_id in seen:
            continue
        seen.add(spot_id)
        effort = place.get("effort") if isinstance(place.get("effort"), dict) else {}
        duration = effort.get("recommended_duration_minutes")
        duration_minutes = int(duration) if isinstance(duration, (int, float)) and 0 < duration <= 600 else None
        info_url = ""
        for source in place.get("sources") or []:
            if not isinstance(source, dict):
                continue
            candidate = str(source.get("url") or "").strip()
            if candidate.startswith(("https://", "http://")):
                info_url = candidate[:2048]
                break
        location = place_location(spot_id, place, location_index)
        public_location = None
        if location:
            latitude = location.get("latitude")
            longitude = location.get("longitude")
            if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
                public_location = {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "point_role": normalize_point_role(location.get("point_role")),
                }
        result.append(
            {
                "spot_id": spot_id,
                "name": name,
                "region": str(place.get("region") or "")[:120],
                "category": str(place.get("category") or "other")[:80],
                "available": (
                    place.get("status") == "active"
                    and place.get("verification", {}).get("status") in {"verified", "partial"}
                ),
                "duration_minutes": duration_minutes,
                "info_url": info_url,
                "location": public_location,
                "visit_info": visit_info_for_place(place),
            }
        )
    return result


def build_app_scenario(
    scenario: dict[str, Any],
    places: list[dict[str, Any]],
    place_index: dict[str, dict[str, Any]],
    *,
    generated_at: date,
    limit: int,
    location_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    traveler_summary = scenario["traveler_summary"]
    scores = rank_places(places, traveler_summary, limit=limit, today=generated_at)
    recommendation = build_recommendation_result(
        scores,
        traveler_summary,
        safety_notice=SAFETY_NOTICE,
        title=scenario["title"],
    )
    recommendation["course"]["route"] = optimize_course_route(
        recommendation["course"]["route"],
        location_index,
    )
    return {
        "id": scenario["id"],
        "label": scenario["label"],
        "title": scenario["title"],
        "traveler_summary": traveler_summary,
        "recommendation": recommendation,
        "places": [
            app_place_result(score, place_index.get(score.spot_id, {}), location_index=location_index)
            for score in scores
        ],
        "condition_variants": build_condition_variants(
            scenario,
            places,
            generated_at=generated_at,
            limit=limit,
            location_index=location_index,
        ),
    }


def build_condition_variants(
    scenario: dict[str, Any],
    places: list[dict[str, Any]],
    *,
    generated_at: date,
    limit: int,
    location_index: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Precompute simple condition-priority routes for static web hosting."""

    traveler_summary = scenario["traveler_summary"]
    base_scores = rank_places(places, traveler_summary, today=generated_at)
    variants: dict[str, dict[str, Any]] = {}
    for key, value in SCENARIO_CONDITION_FOCUS.get(scenario["id"], ()):
        intent = parse_query_intent(value, traveler_summary)
        hits = retrieve_place_candidates(
            places,
            query=value,
            intent={
                "regions": intent.get("regions", []),
                "categories": intent.get("categories", []),
            },
            limit=max(12, limit * 4),
            as_of=generated_at,
        )
        focused_places = [hit["place"] for hit in hits if isinstance(hit.get("place"), dict)]
        focused_scores = rank_places(focused_places, traveler_summary, limit=limit, today=generated_at)
        selected_scores = list(focused_scores)
        selected_ids = {score.spot_id for score in selected_scores}
        for score in base_scores:
            if len(selected_scores) >= limit:
                break
            if score.spot_id in selected_ids:
                continue
            selected_scores.append(score)
            selected_ids.add(score.spot_id)

        recommendation = build_recommendation_result(
            selected_scores,
            traveler_summary,
            safety_notice=SAFETY_NOTICE,
            title=scenario["title"],
        )
        recommendation["course"]["route"] = optimize_course_route(
            recommendation["course"]["route"],
            location_index,
        )
        variant_key = f"{key}:{value}"
        variants[variant_key] = {
            "id": f"{scenario['id']}__condition_focus",
            "label": scenario["label"],
            "title": scenario["title"],
            "focus": {"key": key, "value": value},
            "traveler_summary": traveler_summary,
            "recommendation": recommendation,
            # Route places are resolved from the seed's shared public place index in the browser.
            "places": [],
        }
    return variants


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [value]
    return []


def accessibility_summary(place: dict[str, Any]) -> list[dict[str, str]]:
    accessibility = place.get("accessibility") or {}
    if not isinstance(accessibility, dict):
        return []

    ordered_fields = [field for field in ACCESSIBILITY_FIELDS if field in accessibility]
    ordered_fields.extend(sorted(field for field in accessibility if field not in ACCESSIBILITY_FIELDS))
    summary = []
    for field in ordered_fields:
        value = accessibility.get(field) or {}
        if not isinstance(value, dict):
            value = {}
        state = str(value.get("state") or "unknown")
        summary.append(
            {
                "field": field,
                "label": ACCESSIBILITY_FIELD_LABELS.get(field, field),
                "state": state,
                "state_label": ACCESSIBILITY_STATE_LABELS.get(state, state),
                "note": str(value.get("note") or ""),
            }
        )
    return summary


def effort_summary(place: dict[str, Any]) -> dict[str, Any]:
    effort = place.get("effort") or {}
    if not isinstance(effort, dict):
        effort = {}
    return {
        "walking_level": effort.get("walking_level") or "unknown",
        "recommended_duration_minutes": effort.get("recommended_duration_minutes"),
        "outdoor_exposure": effort.get("outdoor_exposure") or "unknown",
        "weather_sensitivity": effort.get("weather_sensitivity") or "unknown",
    }


def verification_summary(place: dict[str, Any]) -> dict[str, Any]:
    verification = place.get("verification") or {}
    if not isinstance(verification, dict):
        verification = {}
    return {
        "status": verification.get("status") or "needs_check",
        "checked_at": verification.get("checked_at") or "",
        "missing_fields": string_list(verification.get("missing_fields")),
    }


def app_place_result(
    score: PlaceScore,
    place: dict[str, Any],
    *,
    location_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    score_dict = score.to_dict()
    location = place_location(score.spot_id, place, location_index or {})
    return {
        "spot_id": score.spot_id,
        "name": score.name,
        "region": place.get("region", ""),
        "category": place.get("category", "other"),
        "summary": place.get("summary", ""),
        "score": score_dict["score"],
        "fit_reasons": score_dict["fit_reasons"],
        "deduction_reasons": score_dict["deduction_reasons"],
        "check_before_visit": score_dict["check_before_visit"],
        "source_summary": score_dict["source_summary"],
        "blocked": score.blocked,
        "block_reasons": score_dict["block_reasons"],
        "verification_status": place.get("verification", {}).get("status", "needs_check"),
        "verification": verification_summary(place),
        "accessibility": accessibility_summary(place),
        "effort": effort_summary(place),
        "location": location,
        "safety_notes": string_list(place.get("safety_notes")),
        "avoid_for": string_list(place.get("avoid_for")),
        "visit_info": visit_info_for_place(place),
    }


def official_course_exposure(
    course_dataset: dict[str, Any],
    place_index: dict[str, dict[str, Any]],
    *,
    location_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    courses = []
    for course in course_dataset.get("courses", []):
        stops = []
        for stop in course.get("stops", []):
            spot_id = str(stop.get("matched_spot_id") or "")
            place = place_index.get(spot_id, {})
            location = place_location(spot_id, place, location_index) if spot_id else None
            verification = place.get("verification", {}) if isinstance(place, dict) else {}
            stops.append(
                {
                    "order": stop.get("order"),
                    "name": stop.get("name") or place.get("name", ""),
                    "spot_id": spot_id,
                    "matched_name": stop.get("matched_name") or place.get("name", ""),
                    "category": place.get("category", "other"),
                    "verification_status": verification.get("status", "needs_check"),
                    "location_available": bool(location),
                    "promoted_candidate": spot_id.startswith("jeju_tourism_weak_"),
                    "description": str(stop.get("description") or ""),
                    "cautions": str(stop.get("cautions") or ""),
                }
            )

        courses.append(
            {
                "id": course.get("id", ""),
                "title": course.get("title", ""),
                "overview": course.get("overview", ""),
                "recommended_travelers": course.get("recommended_travelers", ""),
                "total_move_minutes": course.get("total_move_minutes"),
                "total_travel_minutes": course.get("total_travel_minutes"),
                "recommendation_by_type": course.get("recommendation_by_type", {}),
                "stops": stops,
            }
        )
    return courses


def place_location(
    spot_id: str,
    place: dict[str, Any],
    location_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    indexed = location_index.get(spot_id)
    if indexed:
        result = dict(indexed)
        result["point_role"] = normalize_point_role(result.get("point_role"))
        return result
    location = place.get("location")
    if isinstance(location, dict):
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            result = dict(location)
            result["point_role"] = normalize_point_role(result.get("point_role"))
            return result
    return None


def public_gate_summary(places: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(place.get("status", "unknown") for place in places)
    verification_counts = Counter(place.get("verification", {}).get("status", "needs_check") for place in places)
    app_candidates = [
        place
        for place in places
        if place.get("status") == "active"
        and place.get("verification", {}).get("status") in {"verified", "partial"}
    ]
    return {
        "total_places": len(places),
        "app_candidate_places": len(app_candidates),
        "status_counts": dict(sorted(status_counts.items())),
        "verification_counts": dict(sorted(verification_counts.items())),
        "excluded_statuses": ["hidden", "blocked", "deprecated"],
        "pending_gate_note": "로드뷰 기반 신규 장소는 사람 최종 검수 전까지 사용자 추천에 사용하지 않습니다.",
    }
