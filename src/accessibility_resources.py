"""Grounded, location-aware search for accessibility support resources in Jeju."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ACCESSIBLE_TOILET = "accessible_toilet"
POWER_WHEELCHAIR_FAST_CHARGER = "power_wheelchair_fast_charger"
SUPPORTED_RESOURCE_TYPES = frozenset(
    {ACCESSIBLE_TOILET, POWER_WHEELCHAIR_FAST_CHARGER}
)
NEARBY_RESOURCE_BEHAVIOR_VERSION = "nearby_accessibility_resource_v1_20260716"
DISTANCE_METHOD = "straight_line_haversine"
EARTH_RADIUS_KM = 6371.0088
MAX_NEARBY_RESULTS = 4

PUBLIC_TOILET_SOURCE_URL = "https://www.data.go.kr/data/15110521/fileData.do"
CHARGER_SOURCE_URL = "https://www.data.go.kr/data/15034533/standard.do"

_CURRENT_LOCATION_TERMS = (
    "현재 위치",
    "내 위치",
    "지금 위치",
    "내가 있는 위치",
    "내가 있는 곳",
    "여기서",
    "내 주변",
    "여기 근처",
    "이 근처",
    "이곳에서",
    "이곳 근처",
)
_SEARCH_TERMS = ("찾아", "찾기", "검색", "알려", "어디", "추천", "있어", "있나")
_TOILET_TERMS = (
    "장애인 화장실",
    "장애인용 화장실",
    "휠체어 화장실",
    "무장애 화장실",
)
_CHARGER_TERMS = (
    "전동휠체어 충전",
    "전동 휠체어 충전",
    "전동스쿠터 충전",
    "전동 스쿠터 충전",
    "휠체어 급속충전",
    "휠체어 급속 충전",
    "보장구 충전",
)


def load_accessibility_resource_snapshot(path: Path) -> dict[str, Any]:
    """Load a generated resource snapshot, failing closed when it is unavailable."""

    if not path.exists():
        return {"metadata": {}, "items": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"metadata": {}, "items": []}

    if isinstance(value, list):
        items = value
        metadata: dict[str, Any] = {}
    elif isinstance(value, dict):
        items = value.get("items")
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    else:
        return {"metadata": {}, "items": []}

    return {
        "metadata": metadata,
        "items": [item for item in (items or []) if isinstance(item, dict)],
    }


def detect_nearby_resource_types(question: Any) -> tuple[str, ...]:
    """Detect explicit nearby searches without hijacking ordinary facility questions."""

    text = _normalized_text(question)
    if not text:
        return ()
    has_proximity = any(_normalized_text(term) in text for term in _CURRENT_LOCATION_TERMS)
    has_search = any(_normalized_text(term) in text for term in _SEARCH_TERMS)
    if not has_proximity or not has_search:
        return ()

    result: list[str] = []
    if any(_normalized_text(term) in text for term in _TOILET_TERMS):
        result.append(ACCESSIBLE_TOILET)
    if any(_normalized_text(term) in text for term in _CHARGER_TERMS):
        result.append(POWER_WHEELCHAIR_FAST_CHARGER)
    return tuple(result)


def build_location_required_reply(question: Any, *, model: str) -> dict[str, Any] | None:
    resource_types = detect_nearby_resource_types(question)
    if not resource_types:
        return None
    labels = [_resource_label(resource_type, exact=True) for resource_type in resource_types]
    return {
        "response_kind": "nearby_resource",
        "status": "location_required",
        "model": model,
        "answer_source": "grounded_accessibility_resource_retrieval",
        "behavior_version": NEARBY_RESOURCE_BEHAVIOR_VERSION,
        "answer": (
            f"현재 위치에서 가까운 {' · '.join(labels)}을 찾으려면 위치 권한이 필요합니다. "
            "좌표는 이번 거리 검색에만 사용하며 대화 기록이나 OpenAI 요청에 넣지 않습니다."
        ),
        "resource_types": list(resource_types),
        "nearby_results": [],
        "followups": [],
        "handoff_checklist": [],
        "safety_note": _resource_safety_note(resource_types),
    }


def search_nearby_accessibility_resources(
    *,
    latitude: float,
    longitude: float,
    resource_types: Sequence[str],
    limit: int = MAX_NEARBY_RESULTS,
    accuracy_meters: float | None = None,
    places: Sequence[Mapping[str, Any]] = (),
    location_index: Mapping[str, Mapping[str, Any]] | None = None,
    public_toilets: Sequence[Mapping[str, Any]] = (),
    chargers: Sequence[Mapping[str, Any]] = (),
    model: str = "deterministic",
) -> dict[str, Any]:
    """Return public, evidence-backed resource cards sorted by straight-line distance."""

    normalized_types = _unique_supported_types(resource_types)
    if not normalized_types:
        raise ValueError("at least one supported resource type is required")
    if not _valid_global_coordinate(latitude, longitude):
        raise ValueError("invalid origin coordinate")

    bounded_limit = max(1, min(int(limit), MAX_NEARBY_RESULTS))
    bounded_accuracy = _bounded_accuracy(accuracy_meters)
    if not _is_jeju_coordinate(latitude, longitude):
        return _nearby_reply(
            status="outside_service_area",
            model=model,
            resource_types=normalized_types,
            results=[],
            available_counts={resource_type: 0 for resource_type in normalized_types},
            accuracy_meters=bounded_accuracy,
            answer="현재 위치가 제주 서비스 범위를 벗어나 있어 가까운 시설을 계산하지 않았습니다.",
        )

    candidates: dict[str, list[dict[str, Any]]] = {
        resource_type: [] for resource_type in normalized_types
    }
    if ACCESSIBLE_TOILET in candidates:
        for row in public_toilets:
            projected = _project_snapshot_resource(row, ACCESSIBLE_TOILET)
            if projected:
                candidates[ACCESSIBLE_TOILET].append(projected)
        candidates[ACCESSIBLE_TOILET].extend(
            _toilet_venue_candidates(places, location_index or {})
        )
    if POWER_WHEELCHAIR_FAST_CHARGER in candidates:
        for row in chargers:
            projected = _project_snapshot_resource(row, POWER_WHEELCHAIR_FAST_CHARGER)
            if projected:
                candidates[POWER_WHEELCHAIR_FAST_CHARGER].append(projected)

    for resource_type, items in candidates.items():
        candidates[resource_type] = _deduplicate_candidates(items)
        for item in candidates[resource_type]:
            distance_km = haversine_km(
                latitude,
                longitude,
                item["latitude"],
                item["longitude"],
            )
            distance_meters = max(0, round(distance_km * 1000))
            item["distance_meters"] = distance_meters
            item["distance_label"] = _distance_label(distance_meters)
        candidates[resource_type].sort(
            key=lambda item: (
                item["distance_meters"],
                _normalized_text(item.get("name")),
                str(item.get("id") or ""),
            )
        )

    results = _balanced_results(candidates, normalized_types, bounded_limit)
    available_counts = {key: len(value) for key, value in candidates.items()}
    if not results:
        status = "resource_data_gap" if all(count == 0 for count in available_counts.values()) else "no_match"
        answer = "연결된 공식 데이터에서 안내할 수 있는 시설을 찾지 못했습니다."
    else:
        status = "success"
        type_summary = " · ".join(
            f"{_resource_label(resource_type, exact=True)} {sum(1 for item in results if item['resource_type'] == resource_type)}곳"
            for resource_type in normalized_types
            if any(item["resource_type"] == resource_type for item in results)
        )
        answer = (
            f"현재 위치 기준 가까운 {type_summary}을 거리순으로 찾았습니다. "
            "표시 거리는 직선거리이며 실제 이동거리와 다를 수 있습니다."
        )

    return _nearby_reply(
        status=status,
        model=model,
        resource_types=normalized_types,
        results=results,
        available_counts=available_counts,
        accuracy_meters=bounded_accuracy,
        answer=answer,
    )


def haversine_km(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> float:
    lat1 = math.radians(float(origin_latitude))
    lat2 = math.radians(float(destination_latitude))
    delta_lat = lat2 - lat1
    delta_lng = math.radians(float(destination_longitude) - float(origin_longitude))
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(min(1.0, math.sqrt(haversine)))


def _toilet_venue_candidates(
    places: Sequence[Mapping[str, Any]],
    location_index: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for place in places:
        if str(place.get("status") or "active").casefold() != "active":
            continue
        accessibility = place.get("accessibility")
        toilet = accessibility.get("accessible_toilet") if isinstance(accessibility, Mapping) else None
        if not isinstance(toilet, Mapping) or str(toilet.get("state") or "").casefold() != "yes":
            continue
        place_id = str(place.get("id") or place.get("spot_id") or "").strip()
        location = location_index.get(place_id)
        if not isinstance(location, Mapping) or not _valid_jeju_coordinate(
            location.get("latitude"), location.get("longitude")
        ):
            continue
        source = _source_for_place_fact(place, str(toilet.get("source_ref") or ""))
        verification = place.get("verification") if isinstance(place.get("verification"), Mapping) else {}
        visit_info = place.get("visit_info") if isinstance(place.get("visit_info"), Mapping) else {}
        candidates.append(
            {
                "id": place_id or f"toilet-venue-{len(candidates) + 1}",
                "resource_type": ACCESSIBLE_TOILET,
                "resource_label": "장애인 화장실 확인 장소",
                "name": _bounded_text(place.get("name"), 120),
                "latitude": round(float(location["latitude"]), 7),
                "longitude": round(float(location["longitude"]), 7),
                "address": _bounded_text(visit_info.get("address"), 240),
                "detail": _bounded_text(toilet.get("note"), 260),
                "operating_hours": _bounded_text(visit_info.get("operating_hours"), 120),
                "phone": _bounded_text(visit_info.get("phone"), 60),
                "managing_organization": "",
                "capacity": None,
                "accessibility_note": (
                    "장애인 화장실 보유 정보가 확인된 관광지이며, 좌표는 화장실 자체가 아닌 장소 대표점입니다."
                ),
                "coordinate_basis": "venue_representative_point",
                "verification_status": _verification_status(verification.get("status")),
                "checked_at": _bounded_text(verification.get("checked_at"), 20),
                "source_title": _bounded_text(source.get("title"), 180),
                "source_url": _safe_public_url(source.get("url")),
            }
        )
    return candidates


def _project_snapshot_resource(
    row: Mapping[str, Any], expected_type: str
) -> dict[str, Any] | None:
    if str(row.get("resource_type") or expected_type) != expected_type:
        return None
    if not _valid_jeju_coordinate(row.get("latitude"), row.get("longitude")):
        return None
    name = _bounded_text(row.get("name"), 120)
    if not name:
        return None

    if expected_type == ACCESSIBLE_TOILET:
        fixture_count = _optional_nonnegative_int(
            row.get("accessible_fixture_count") or row.get("capacity")
        )
        detail = _bounded_text(row.get("detail"), 260) or (
            f"장애인용 변기·소변기 {fixture_count}개 등록"
            if fixture_count is not None
            else "장애인용 위생시설 보유 정보 등록"
        )
        resource_label = "장애인 화장실"
        accessibility_note = "공공데이터에 장애인용 위생시설 수가 1개 이상 등록된 화장실입니다."
        coordinate_basis = "facility_coordinate"
    else:
        fixture_count = _optional_nonnegative_int(row.get("capacity"))
        detail = _bounded_text(
            row.get("installation_location") or row.get("detail"), 260
        )
        resource_label = "전동휠체어 급속충전기"
        accessibility_note = "공공데이터 등록 위치이며 고장·점유 상태는 실시간 정보가 아닙니다."
        coordinate_basis = "facility_coordinate"

    operating_hours = row.get("operating_hours")
    if isinstance(operating_hours, Mapping):
        operating_hours_text = _format_operating_hours(operating_hours)
    else:
        operating_hours_text = _bounded_text(
            operating_hours or row.get("opening_hours"), 160
        )

    return {
        "id": _bounded_text(row.get("id"), 140) or f"{expected_type}-{name}",
        "resource_type": expected_type,
        "resource_label": resource_label,
        "name": name,
        "latitude": round(float(row["latitude"]), 7),
        "longitude": round(float(row["longitude"]), 7),
        "address": _bounded_text(row.get("address") or row.get("road_address"), 240),
        "detail": detail,
        "operating_hours": operating_hours_text,
        "phone": _bounded_text(row.get("phone"), 60),
        "managing_organization": _bounded_text(row.get("managing_organization"), 120),
        "capacity": fixture_count,
        "accessibility_note": accessibility_note,
        "coordinate_basis": coordinate_basis,
        "verification_status": "public_data",
        "checked_at": _bounded_text(
            row.get("checked_at") or row.get("reference_date"), 20
        ),
        "source_title": _bounded_text(
            row.get("source_title")
            or (
                "제주특별자치도 제주시_공중화장실"
                if expected_type == ACCESSIBLE_TOILET
                else "전국전동휠체어급속충전기표준데이터"
            ),
            180,
        ),
        "source_url": _safe_public_url(
            row.get("source_url")
            or (PUBLIC_TOILET_SOURCE_URL if expected_type == ACCESSIBLE_TOILET else CHARGER_SOURCE_URL)
        ),
    }


def _nearby_reply(
    *,
    status: str,
    model: str,
    resource_types: Sequence[str],
    results: Sequence[Mapping[str, Any]],
    available_counts: Mapping[str, int],
    accuracy_meters: int | None,
    answer: str,
) -> dict[str, Any]:
    return {
        "response_kind": "nearby_resource",
        "status": status,
        "model": model,
        "answer_source": "grounded_accessibility_resource_retrieval",
        "behavior_version": NEARBY_RESOURCE_BEHAVIOR_VERSION,
        "answer": answer,
        "resource_types": list(resource_types),
        "nearby_results": [dict(item) for item in results],
        "result_counts": dict(available_counts),
        "origin_accuracy_meters": accuracy_meters,
        "retrieval": {
            "engine": "structured_geospatial_evidence_v1",
            "distance_method": DISTANCE_METHOD,
            "evidence_policy": "public_source_required",
            "returned": len(results),
        },
        "followups": ["운영 여부를 확인할 전화 문장을 만들어줘"] if results else [],
        "handoff_checklist": ["방문 전 운영 여부 확인", "실제 이동 경로와 출입구 위치 확인"] if results else [],
        "safety_note": _resource_safety_note(resource_types),
    }


def _balanced_results(
    candidates: Mapping[str, Sequence[dict[str, Any]]],
    resource_types: Sequence[str],
    limit: int,
) -> list[dict[str, Any]]:
    if len(resource_types) == 1:
        return [dict(item) for item in candidates.get(resource_types[0], ())[:limit]]

    selected: list[dict[str, Any]] = []
    per_type = max(1, limit // len(resource_types))
    selected_ids: set[str] = set()
    for resource_type in resource_types:
        for item in candidates.get(resource_type, ())[:per_type]:
            selected.append(dict(item))
            selected_ids.add(f"{resource_type}:{item.get('id')}")

    remaining = sorted(
        (
            dict(item)
            for resource_type in resource_types
            for item in candidates.get(resource_type, ())
            if f"{resource_type}:{item.get('id')}" not in selected_ids
        ),
        key=lambda item: (item["distance_meters"], _normalized_text(item.get("name"))),
    )
    selected.extend(remaining[: max(0, limit - len(selected))])
    selected.sort(key=lambda item: (item["distance_meters"], _normalized_text(item.get("name"))))
    return selected[:limit]


def _deduplicate_candidates(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        key = (
            item.get("resource_type"),
            round(float(item["latitude"]), 5),
            round(float(item["longitude"]), 5),
            _normalized_text(item.get("address")),
        )
        current = selected.get(key)
        current_capacity = current.get("capacity") if current else None
        candidate_capacity = item.get("capacity")
        if current is None or (candidate_capacity or 0) > (current_capacity or 0):
            selected[key] = item
    return list(selected.values())


def _source_for_place_fact(place: Mapping[str, Any], source_ref: str) -> dict[str, Any]:
    sources = [source for source in (place.get("sources") or []) if isinstance(source, Mapping)]
    hints = {
        "easyjeju": ("easyjeju", "이지제주"),
        "jeju_roadview_facility_status": ("15109153", "로드뷰"),
        "open_tourism": ("access.visitkorea", "열린관광"),
        "tourism_weak_recommendation_courses": ("15117357", "관광약자"),
    }.get(source_ref.casefold(), (source_ref,))
    normalized_hints = tuple(_normalized_text(hint) for hint in hints if hint)
    for source in sources:
        haystack = _normalized_text(f"{source.get('title')} {source.get('url')}")
        if any(hint and hint in haystack for hint in normalized_hints):
            return dict(source)
    return dict(sources[0]) if sources else {}


def _format_operating_hours(value: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (("weekday", "평일"), ("saturday", "토"), ("holiday", "공휴일")):
        item = value.get(key)
        if isinstance(item, Mapping):
            start = _bounded_text(item.get("start") or item.get("opening"), 12)
            end = _bounded_text(item.get("end") or item.get("closing"), 12)
            if start == "00:00" and end == "00:00":
                continue
            if start or end:
                parts.append(f"{label} {start or '?'}~{end or '?'}")
        elif item:
            parts.append(f"{label} {_bounded_text(item, 30)}")
    return " · ".join(parts)[:160]


def _resource_safety_note(resource_types: Sequence[str]) -> str:
    notes = ["거리 표시는 좌표 간 직선거리이며 실제 이동거리·무장애 경로와 다를 수 있습니다."]
    if ACCESSIBLE_TOILET in resource_types:
        notes.append("공중화장실 공공데이터는 현재 제주시 제공 범위이며, 개방·사용 가능 여부는 방문 전 관리기관에 확인해 주세요.")
    if POWER_WHEELCHAIR_FAST_CHARGER in resource_types:
        notes.append("충전기 고장·점유 상태는 실시간 정보가 아니므로 방문 전 전화 확인을 권장합니다.")
    return " ".join(notes)


def _resource_label(resource_type: str, *, exact: bool = False) -> str:
    if resource_type == ACCESSIBLE_TOILET:
        return "장애인 화장실" if exact else "장애인 화장실 확인 장소"
    return "전동휠체어 급속충전기"


def _distance_label(distance_meters: int) -> str:
    if distance_meters < 1000:
        rounded = max(10, int(round(distance_meters / 10.0) * 10))
        return f"{rounded:,}m"
    return f"{distance_meters / 1000:.1f}km"


def _unique_supported_types(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized in SUPPORTED_RESOURCE_TYPES and normalized not in result:
            result.append(normalized)
    return tuple(result)


def _bounded_accuracy(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return min(round(number), 100_000)


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _valid_global_coordinate(latitude: Any, longitude: Any) -> bool:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return False
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180


def _is_jeju_coordinate(latitude: Any, longitude: Any) -> bool:
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    return 32.8 <= lat <= 34.0 and 125.8 <= lng <= 127.2


def _valid_jeju_coordinate(latitude: Any, longitude: Any) -> bool:
    return _valid_global_coordinate(latitude, longitude) and _is_jeju_coordinate(latitude, longitude)


def _verification_status(value: Any) -> str:
    normalized = str(value or "needs_check").strip().casefold()
    return normalized if normalized in {"verified", "partial", "needs_check"} else "needs_check"


def _safe_public_url(value: Any) -> str:
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else ""


def _bounded_text(value: Any, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_length]


def _normalized_text(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", str(value or "")).casefold()
