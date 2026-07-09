"""Normalize 제주관광공사 tourism-weak recommendation course data."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any


SOURCE_TITLE = "제주관광공사_관광 약자 유형별 제주관광 추천코스"
SOURCE_URL = "https://www.data.go.kr/data/15117357/fileData.do"
SOURCE_PROVIDER = "제주관광공사"
SOURCE_LICENSE = "공공저작물 제4유형"

TRAVELER_RECOMMENDATION_COLUMNS = {
    "wheelchair_user": "관광약자 유형별 관광 추천(지체장애)",
    "visual_impairment": "관광약자 유형별 관광 추천(시각장애)",
    "hearing_impairment": "관광약자 유형별 관광 추천(청각장애)",
    "senior_or_pregnant": "관광약자 유형별 관광 추천(노인_임산부)",
    "stroller_family": "관광약자 유형별 관광 추천(영유아)",
}

TRAVELER_TYPE_LABELS = {
    "wheelchair_user": "지체장애",
    "visual_impairment": "시각장애",
    "hearing_impairment": "청각장애",
    "senior_or_pregnant": "노인·임산부",
    "stroller_family": "영유아",
}

TRAVELER_TYPE_TERMS = {
    "wheelchair_user": {"wheelchair_user", "휠체어", "지체장애"},
    "visual_impairment": {"visual_impairment", "시각장애", "시각"},
    "hearing_impairment": {"hearing_impairment", "청각장애", "청각"},
    "senior_or_pregnant": {"senior", "pregnant_traveler", "노인", "고령", "임산부", "임신"},
    "stroller_family": {"stroller_family", "영유아", "유모차", "아이", "가족"},
}

RECOMMENDATION_BONUS = {
    "적극추천": 6,
    "추천": 4,
    "조건부권장": 2,
}

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

TOURISM_WEAK_SOURCE_REF = "tourism_weak_recommendation_courses"


def normalize_place_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value or "").casefold()


PLACE_NAME_ALIASES = {
    normalize_place_key("새연교(새섬)"): normalize_place_key("새연교"),
    normalize_place_key("서귀포 치유의 숲"): normalize_place_key("서귀포 치유의숲"),
    normalize_place_key("붉은오름 자연휴양림"): normalize_place_key("붉은오름자연휴양림"),
    normalize_place_key("천지연 폭포"): normalize_place_key("천지연폭포"),
    normalize_place_key("오설록"): normalize_place_key("오설록 티 뮤지엄"),
    normalize_place_key("해녀박물관"): normalize_place_key("제주해녀박물관"),
    normalize_place_key("항파두리항몽유적지"): normalize_place_key("항몽유적지"),
    normalize_place_key("생각하는정원"): normalize_place_key("생각하는 정원"),
    normalize_place_key("탑동"): normalize_place_key("탑동해변공연장"),
    normalize_place_key("동문시장"): normalize_place_key("동문재래시장"),
    normalize_place_key("올레6코스"): normalize_place_key("올레길6코스 휠체어구간"),
}


def read_course_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def build_tourism_weak_course_dataset(
    rows: list[dict[str, str]],
    places: list[dict[str, Any]],
) -> dict[str, Any]:
    place_index = _place_index(places)
    courses: list[dict[str, Any]] = []
    place_references: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched: dict[str, dict[str, Any]] = {}
    matched_stop_count = 0
    total_stop_count = 0

    for course_index, row in enumerate(rows, start=1):
        course_id = f"tourism_weak_course_{course_index:03d}"
        recommendations = _course_recommendations(row)
        stops = []
        for order in range(1, 5):
            source_name = _clean_text(row.get(f"코스{order}", ""))
            if not source_name or source_name == "없음":
                continue

            total_stop_count += 1
            matched_place = _match_place(source_name, place_index)
            stop = {
                "order": order,
                "name": source_name,
                "description": _clean_text(row.get(f"코스{order} 설명", "")),
                "cautions": _clean_text(row.get(f"코스{order} 유의사항", "")),
                "hashtags": _split_tags(row.get(f"코스{order} 연관 해시태그", "")),
                "mandatory_facilities": _split_tags(row.get(f"의무시설정보(코스{order})", "")),
                "matched_spot_id": matched_place.get("id", "") if matched_place else "",
                "matched_name": matched_place.get("name", "") if matched_place else "",
            }
            stops.append(stop)

            if matched_place:
                matched_stop_count += 1
                place_references[matched_place["id"]].append(
                    {
                        "course_id": course_id,
                        "course_title": _clean_text(row.get("관광추천코스", "")),
                        "order": order,
                        "source_place_name": source_name,
                        "recommendation_by_type": recommendations,
                        "description": stop["description"],
                        "cautions": stop["cautions"],
                        "hashtags": stop["hashtags"],
                        "mandatory_facilities": stop["mandatory_facilities"],
                        "total_move_minutes": _int_or_none(row.get("총이동시간(분)")),
                        "total_travel_minutes": _int_or_none(row.get("총여행시간(분)")),
                    }
                )
            else:
                unmatched.setdefault(
                    normalize_place_key(source_name),
                    {"name": source_name, "course_titles": []},
                )["course_titles"].append(_clean_text(row.get("관광추천코스", "")))

        courses.append(
            {
                "id": course_id,
                "title": _clean_text(row.get("관광추천코스", "")),
                "overview": _clean_text(row.get("코스개요", "")),
                "recommended_travelers": _clean_text(row.get("추천여행자", "")),
                "total_move_minutes": _int_or_none(row.get("총이동시간(분)")),
                "total_travel_minutes": _int_or_none(row.get("총여행시간(분)")),
                "recommendation_by_type": recommendations,
                "stops": stops,
            }
        )

    return {
        "source": {
            "title": SOURCE_TITLE,
            "url": SOURCE_URL,
            "provider": SOURCE_PROVIDER,
            "license": SOURCE_LICENSE,
        },
        "summary": {
            "courses": len(courses),
            "stops": total_stop_count,
            "matched_stops": matched_stop_count,
            "matched_places": len(place_references),
            "unmatched_places": len(unmatched),
        },
        "courses": courses,
        "place_references": dict(sorted(place_references.items())),
        "unmatched_places": sorted(unmatched.values(), key=lambda item: item["name"]),
    }


def load_tourism_weak_courses(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_tourism_weak_courses(dataset: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_promoted_course_place_cards(
    course_dataset: dict[str, Any],
    existing_places: list[dict[str, Any]],
    *,
    checked_at: str = "2026-05-28",
) -> list[dict[str, Any]]:
    """Build conservative place cards for unmatched public recommendation stops."""

    existing_names = {normalize_place_key(place.get("name", "")) for place in existing_places}
    existing_ids = {str(place.get("id") or "") for place in existing_places}
    grouped_stops: dict[str, dict[str, Any]] = {}

    for course in course_dataset.get("courses", []):
        for stop in course.get("stops", []):
            name = _clean_text(stop.get("name", ""))
            key = normalize_place_key(name)
            if not key or stop.get("matched_spot_id") or key in existing_names:
                continue

            grouped = grouped_stops.setdefault(
                key,
                {
                    "name": name,
                    "course_ids": [],
                    "course_titles": [],
                    "recommendations": [],
                    "descriptions": [],
                    "cautions": [],
                    "hashtags": [],
                    "mandatory_facilities": [],
                    "total_travel_minutes": [],
                },
            )
            grouped["course_ids"].append(str(course.get("id") or ""))
            grouped["course_titles"].append(str(course.get("title") or ""))
            grouped["recommendations"].append(course.get("recommendation_by_type", {}))
            grouped["descriptions"].append(str(stop.get("description") or ""))
            grouped["cautions"].append(str(stop.get("cautions") or ""))
            grouped["hashtags"].extend(stop.get("hashtags", []))
            grouped["mandatory_facilities"].extend(stop.get("mandatory_facilities", []))
            if course.get("total_travel_minutes") is not None:
                grouped["total_travel_minutes"].append(course.get("total_travel_minutes"))

    cards = []
    for index, grouped in enumerate(sorted(grouped_stops.values(), key=lambda item: item["name"]), start=1):
        card_id = f"jeju_tourism_weak_{index:03d}"
        while card_id in existing_ids:
            index += 1
            card_id = f"jeju_tourism_weak_{index:03d}"
        existing_ids.add(card_id)
        cards.append(_promoted_course_place_card(card_id, grouped, checked_at=checked_at))
    return cards


def augment_places_with_tourism_weak_courses(
    places: list[dict[str, Any]],
    course_dataset: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not course_dataset:
        return [deepcopy(place) for place in places]

    references = course_dataset.get("place_references", {})
    augmented = []
    for place in places:
        copied = deepcopy(place)
        place_refs = references.get(place.get("id", ""), [])
        if place_refs:
            copied["tourism_weak_course_references"] = deepcopy(place_refs)
            copied.setdefault("sources", [])
            if not any(source.get("url") == SOURCE_URL for source in copied["sources"]):
                copied["sources"].append({"title": SOURCE_TITLE, "url": SOURCE_URL, "type": "public_agency"})
        augmented.append(copied)
    return augmented


def tourism_weak_course_bonus(
    place: dict[str, Any],
    traveler_summary: dict[str, list[str]],
    fit_reasons: list[str],
    check_before_visit: list[str],
) -> int:
    references = place.get("tourism_weak_course_references", [])
    if not references:
        return 0

    active_types = _active_traveler_types(traveler_summary)
    if not active_types:
        return 0

    best: tuple[int, str, str, str] | None = None
    for reference in references:
        recommendations = reference.get("recommendation_by_type", {})
        for traveler_type in active_types:
            label = str(recommendations.get(traveler_type) or "").strip()
            bonus = RECOMMENDATION_BONUS.get(label, 0)
            if bonus <= 0:
                continue
            candidate = (
                bonus,
                TRAVELER_TYPE_LABELS.get(traveler_type, traveler_type),
                label,
                str(reference.get("course_title") or ""),
            )
            if best is None or candidate[0] > best[0]:
                best = candidate

    if best is None:
        return 0

    bonus, traveler_label, recommendation_label, course_title = best
    fit_reasons.append(
        f"제주관광공사 관광약자 추천코스 '{course_title}'에 포함되어 {traveler_label} 유형 {recommendation_label} 근거가 있습니다."
    )
    if recommendation_label == "조건부권장":
        check_before_visit.append("공공 추천코스의 조건부 권장 사유와 현장 유의사항")
    return bonus


def _promoted_course_place_card(card_id: str, grouped: dict[str, Any], *, checked_at: str) -> dict[str, Any]:
    name = grouped["name"]
    descriptions = _unique(_clean_text(item) for item in grouped["descriptions"])
    cautions = _unique(_clean_text(item) for item in grouped["cautions"])
    hashtags = _unique(_clean_text(item) for item in grouped["hashtags"])
    facilities = _unique(_clean_text(item) for item in grouped["mandatory_facilities"])
    course_titles = _unique(_clean_text(item) for item in grouped["course_titles"])
    text = " ".join([name, *descriptions, *cautions, *hashtags, *facilities])
    category = _infer_course_place_category(name, text)
    accessibility = _course_accessibility_fields(facilities, text)
    missing_fields = [
        field
        for field in ACCESSIBILITY_FIELDS
        if accessibility[field]["state"] in {"unknown", "needs_check"}
    ]
    situation_tags = _course_situation_tags(category, text, accessibility)
    verification_status = "partial" if len(missing_fields) <= 5 else "needs_check"

    return {
        "id": card_id,
        "name": name,
        "region": "제주특별자치도",
        "category": category,
        "situation_tags": situation_tags,
        "summary": _course_place_summary(name, descriptions, course_titles),
        "recommended_for": _recommended_for_from_course_recommendations(grouped["recommendations"]),
        "avoid_for": _course_avoid_for(category, cautions),
        "accessibility": accessibility,
        "effort": _course_effort(category, text, grouped["total_travel_minutes"]),
        "sources": [
            {
                "title": SOURCE_TITLE,
                "url": SOURCE_URL,
                "type": "public_agency",
            }
        ],
        "verification": {
            "status": verification_status,
            "checked_at": checked_at,
            "checked_by": "tourism_weak_course_limited_promotion",
            "missing_fields": missing_fields,
        },
        "status": "active",
        "safety_notes": _course_safety_notes(cautions),
        "operator_notes": (
            "제주관광공사 관광약자 추천코스 원문을 기반으로 제한 승급한 장소 카드. "
            f"포함 코스: {', '.join(course_titles)}. "
            "장소 단위 세부 접근성은 현장 또는 추가 공식 출처 확인 전까지 보수적으로 표시."
        ),
    }


def _course_place_summary(name: str, descriptions: list[str], course_titles: list[str]) -> str:
    if descriptions:
        return descriptions[0]
    if course_titles:
        return f"제주관광공사 관광약자 추천코스 '{course_titles[0]}'에 포함된 장소."
    return f"제주관광공사 관광약자 추천코스에 포함된 장소: {name}."


def _course_avoid_for(category: str, cautions: list[str]) -> list[str]:
    avoid = [
        "공식 추천코스 원문 외 세부 접근성 확인 없이 방문하기 어려운 사용자",
        "장애인 화장실, 주차, 경사·단차 정보가 반드시 확정되어야 하는 사용자",
    ]
    if category in {"sea", "oreum"}:
        avoid.append("강풍·우천·장시간 야외 노출이 부담되는 사용자")
    if any(_contains_any(caution, {"계단", "급경사", "가파르", "불가능", "진입 어려움"}) for caution in cautions):
        avoid.append("경사·계단·단차가 있으면 이동이 어려운 사용자")
    return _unique(avoid)


def _course_safety_notes(cautions: list[str]) -> list[str]:
    notes = [caution for caution in cautions if caution]
    notes.append("공공 추천코스에 포함된 장소이나 최신 운영 여부와 현장 동선은 방문 전 확인 필요")
    notes.append("장애인 화장실, 주차, 경사·단차, 바닥 상태는 사용자 조건에 맞춰 재확인 필요")
    return _unique(notes)


def _recommended_for_from_course_recommendations(recommendations: list[dict[str, str]]) -> list[str]:
    result: list[str] = []
    for recommendation in recommendations:
        if recommendation.get("wheelchair_user") in RECOMMENDATION_BONUS:
            result.extend(["wheelchair_user", "slow_walker", "caregiver_group"])
        if recommendation.get("senior_or_pregnant") in RECOMMENDATION_BONUS:
            result.extend(["senior", "pregnant_traveler", "caregiver_group"])
        if recommendation.get("stroller_family") in RECOMMENDATION_BONUS:
            result.extend(["stroller_family", "caregiver_group"])
    return _unique(result) or ["caregiver_group"]


def _course_accessibility_fields(facilities: list[str], text: str) -> dict[str, dict[str, Any]]:
    facilities_text = " ".join(facilities)
    toilet_state = _facility_yes_or_partial(
        facilities_text,
        text,
        positive_terms={"장애인 화장실", "장애인화장실"},
        caution_terms={"좁", "진입 불가", "미설치", "없음", "고장", "낙후", "일반 화장실만"},
    )
    parking_state = "yes" if _contains_any(facilities_text, {"장애인 전용 주차구역", "장애인 주차"}) else "unknown"
    if parking_state == "yes" and _contains_any(text, {"주차공간 많지", "주차시설이 미흡", "주차장에 해수욕장 건너편"}):
        parking_state = "partial"

    path_evidence = _contains_any(facilities_text, {"주 출입구 접근로", "주 출입구 높이 차이 제거", "출입문", "복도", "승강기"})
    slope_terms = {"계단", "경사", "단차", "가파르", "오르막", "내리막", "급경사"}
    surface_terms = {"흙길", "돌길", "자갈", "미끄", "바닥", "요철", "모래", "배수로", "짚길", "암석"}

    return {
        "wheelchair_access": {
            "state": "partial" if path_evidence or _contains_any(text, {"휠체어", "보장구", "유아차"}) else "needs_check",
            "note": "공식 추천코스 원문에 접근 가능 요소가 있으나 전체 동선은 현장 확인 필요" if path_evidence else "공식 추천코스 원문만으로 전체 휠체어 접근성을 확정하기 어려움",
            "source_ref": TOURISM_WEAK_SOURCE_REF if path_evidence else None,
        },
        "accessible_toilet": {
            "state": toilet_state,
            "note": _state_note(toilet_state, "장애인 화장실"),
            "source_ref": TOURISM_WEAK_SOURCE_REF if toilet_state in {"yes", "partial", "no"} else None,
        },
        "parking": {
            "state": parking_state,
            "note": _state_note(parking_state, "장애인 전용 주차구역"),
            "source_ref": TOURISM_WEAK_SOURCE_REF if parking_state in {"yes", "partial"} else None,
        },
        "slope_or_stairs": {
            "state": "partial" if _contains_any(text, slope_terms) or path_evidence else "needs_check",
            "note": "원문에 경사·계단·단차 또는 높이 차이 제거 관련 정보가 있어 사용자 조건별 확인 필요",
            "source_ref": TOURISM_WEAK_SOURCE_REF if _contains_any(text, slope_terms) or path_evidence else None,
        },
        "rest_area": {
            "state": "partial" if _contains_any(text, {"쉼터", "벤치", "휴식", "공원", "데크", "광장", "마을"}) else "unknown",
            "note": "휴식 가능 요소가 원문에 언급되나 좌석 위치와 이용 가능성은 확인 필요",
            "source_ref": TOURISM_WEAK_SOURCE_REF if _contains_any(text, {"쉼터", "벤치", "휴식", "공원", "데크", "광장", "마을"}) else None,
        },
        "rental_or_assistance": {
            "state": "unknown",
            "note": "휠체어·유아차 대여 또는 현장 보조 가능 여부는 원문만으로 확정 불가",
            "source_ref": None,
        },
        "surface_condition": {
            "state": "partial" if _contains_any(text, surface_terms) else "needs_check",
            "note": "원문에 바닥 또는 노면 관련 주의사항이 있어 이동 보조기기 조건별 확인 필요" if _contains_any(text, surface_terms) else "바닥 상태는 추가 확인 필요",
            "source_ref": TOURISM_WEAK_SOURCE_REF if _contains_any(text, surface_terms) else None,
        },
        "crowd_level": {
            "state": "needs_check" if _contains_any(text, {"통행인이 많", "이용객이 많", "탐방객이 많", "번잡", "혼잡"}) else "unknown",
            "note": "혼잡도는 계절, 시간대, 행사 여부에 따라 달라 방문 전 확인 필요",
            "source_ref": None,
        },
    }


def _facility_yes_or_partial(
    facilities_text: str,
    text: str,
    *,
    positive_terms: set[str],
    caution_terms: set[str],
) -> str:
    if _contains_any(text, {"장애인전용 화장실(칸) 없음", "장애인 전용은 없음", "일반 화장실만"}):
        return "no"
    if not _contains_any(facilities_text, positive_terms):
        return "unknown"
    if _contains_any(text, caution_terms):
        return "partial"
    return "yes"


def _state_note(state: str, label: str) -> str:
    if state == "yes":
        return f"공식 추천코스 의무시설 정보에 {label} 포함"
    if state == "partial":
        return f"공식 추천코스에 {label} 근거가 있으나 원문 유의사항 확인 필요"
    if state == "no":
        return f"공식 추천코스 원문상 {label} 이용 제약 또는 부재 정보가 있음"
    return f"{label} 정보는 공식 추천코스 원문만으로 확정 불가"


def _course_effort(category: str, text: str, travel_minutes: list[int]) -> dict[str, Any]:
    if _contains_any(text, {"계단", "급경사", "가파르", "정상", "긴 탐방로"}):
        walking = "high" if category == "oreum" else "medium"
    elif _contains_any(text, {"평탄", "정돈", "데크", "완만", "어렵지 않게", "수월"}):
        walking = "low"
    else:
        walking = "unknown"

    if category in {"indoor", "culture"}:
        outdoor = "low"
        weather = "low"
    elif category in {"sea", "oreum"}:
        outdoor = "high"
        weather = "high"
    elif category in {"forest", "rest_area"}:
        outdoor = "medium"
        weather = "medium"
    else:
        outdoor = "unknown"
        weather = "unknown"

    return {
        "walking_level": walking,
        "recommended_duration_minutes": _duration_for_course_place(category, travel_minutes),
        "outdoor_exposure": outdoor,
        "weather_sensitivity": weather,
    }


def _duration_for_course_place(category: str, travel_minutes: list[int]) -> int | None:
    if travel_minutes:
        average = sum(int(value) for value in travel_minutes) // len(travel_minutes)
        return max(30, min(90, average // 3))
    return {
        "indoor": 50,
        "culture": 50,
        "sea": 35,
        "oreum": 60,
        "forest": 60,
        "rest_area": 45,
        "food_market": 45,
    }.get(category)


def _course_situation_tags(
    category: str,
    text: str,
    accessibility: dict[str, dict[str, Any]],
) -> list[str]:
    tags: list[str] = []
    if category in {"indoor", "culture"}:
        tags.append("indoor")
    if category in {"sea", "forest", "oreum", "rest_area"}:
        tags.extend(["outdoor", "weather_sensitive"])
    if category in {"sea", "oreum", "rest_area"}:
        tags.append("scenic_view")
    if category == "food_market":
        tags.extend(["food_focused", "crowded_possible"])
    if _contains_any(text, {"혼잡", "이용객이 많", "통행인이 많", "번잡"}):
        tags.append("crowded_possible")
    if accessibility["accessible_toilet"]["state"] in {"yes", "partial"}:
        tags.append("restroom_important")
    return _unique(tags)


def _infer_course_place_category(name: str, text: str) -> str:
    if _contains_any(name, {"오일장", "시장"}):
        return "food_market"
    if _contains_any(name, {"해변", "해수욕장", "해안", "포구", "서빈백사", "쇠소깍", "싱계물"}):
        return "sea"
    if _contains_any(name, {"오름", "일출봉", "산굼부리"}) or any(part.endswith("봉") for part in re.split(r"[\s,()/·_-]+", name) if part):
        return "oreum"
    if _contains_any(name, {"숲", "휴양림", "곶자왈", "비자림"}):
        return "forest"
    if _contains_any(name, {"박물관", "미술관", "기념관", "항공우주"}):
        return "indoor"
    if _contains_any(name, {"4.3", "평화", "문화예술", "역사", "유적"}):
        return "culture"
    if _contains_any(name, {"공원", "정원", "마을", "목장", "다원", "방림원", "보롬왓", "카멜리아힐", "못", "밭담길"}):
        return "rest_area"
    if _contains_any(text, {"해변", "해수욕장", "해안", "포구"}):
        return "sea"
    if _contains_any(text, {"박물관", "미술관", "기념관", "전시", "출입문", "복도", "승강기"}):
        return "indoor"
    if _contains_any(text, {"숲", "휴양림", "곶자왈"}):
        return "forest"
    return "other"


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _place_index(places: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index = {normalize_place_key(place.get("name", "")): place for place in places}
    for alias, target in PLACE_NAME_ALIASES.items():
        if target in index:
            index[alias] = index[target]
    return index


def _match_place(name: str, place_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = normalize_place_key(name)
    if not key:
        return None
    if key in PLACE_NAME_ALIASES:
        key = PLACE_NAME_ALIASES[key]
    if key in place_index:
        return place_index[key]
    for candidate_key, place in place_index.items():
        if key in candidate_key or candidate_key in key:
            return place
    return None


def _course_recommendations(row: dict[str, str]) -> dict[str, str]:
    result = {}
    for traveler_type, column in TRAVELER_RECOMMENDATION_COLUMNS.items():
        value = _clean_text(row.get(column, ""))
        if value and value != "없음":
            result[traveler_type] = value
    return result


def _active_traveler_types(traveler_summary: dict[str, list[str]]) -> list[str]:
    terms = set()
    for value in traveler_summary.values():
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip().casefold()
                if text:
                    terms.add(text)
    active = []
    for traveler_type, triggers in TRAVELER_TYPE_TERMS.items():
        if any(trigger.casefold() in term or term in trigger.casefold() for term in terms for trigger in triggers):
            active.append(traveler_type)
    return active


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split_tags(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text or text in {"없음", "스팟(의무시설 없음)"}:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _unique(values: Any) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        if value is None or value == "":
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
