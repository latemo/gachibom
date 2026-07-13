"""Location enrichment for app and API place results."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


POINT_ROLES = frozenset(
    {
        "poi",
        "facility",
        "route_start",
        "route_start_end",
        "route_end_reference",
        "viewpoint",
    }
)
DEFAULT_POINT_ROLE = "poi"


def normalize_point_role(value: Any) -> str:
    point_role = str(value or "").strip()
    return point_role if point_role in POINT_ROLES else DEFAULT_POINT_ROLE


def load_json_list(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    value = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def build_place_location_index(
    places: Iterable[Mapping[str, Any]],
    *,
    roadview_metadata: Iterable[Mapping[str, Any]] | None = None,
    overrides: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    roadview_index = roadview_name_index(roadview_metadata or [])
    override_index = {
        str(item.get("spot_id") or item.get("id") or ""): item
        for item in overrides or []
        if item.get("spot_id") or item.get("id")
    }

    locations: dict[str, dict[str, Any]] = {}
    for place in places:
        spot_id = str(place.get("id") or place.get("spot_id") or "")
        if not spot_id:
            continue
        override = override_index.get(spot_id)
        if override:
            location = location_from_override(override)
        else:
            location = location_from_roadview(place, roadview_index)
        if location:
            locations[spot_id] = location
    return locations


def load_place_location_index(
    places: Iterable[Mapping[str, Any]],
    *,
    roadview_metadata_path: str | Path | None = None,
    overrides_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    return build_place_location_index(
        places,
        roadview_metadata=load_json_list(roadview_metadata_path) if roadview_metadata_path else [],
        overrides=load_json_list(overrides_path) if overrides_path else [],
    )


def roadview_name_index(metadata_rows: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in metadata_rows:
        key = normalize_place_name(row.get("tourist_name"))
        if key:
            by_name[key].append(row)
    return dict(by_name)


def location_from_roadview(
    place: Mapping[str, Any],
    roadview_index: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any] | None:
    place_name = str(place.get("name") or "")
    place_key = normalize_place_name(place_name)
    rows = roadview_index.get(place_key)
    matched_name = place_name
    match_method = "roadview_exact_name"

    if not rows:
        candidates: list[tuple[int, str, list[Mapping[str, Any]]]] = []
        for tourist_key, tourist_rows in roadview_index.items():
            if place_key and (place_key in tourist_key or tourist_key in place_key):
                candidates.append((abs(len(place_key) - len(tourist_key)), tourist_key, tourist_rows))
        if candidates:
            _, matched_key, rows = sorted(candidates, key=lambda item: item[0])[0]
            matched_name = str(rows[0].get("tourist_name") or matched_key)
            match_method = "roadview_partial_name"

    if not rows:
        return None

    coordinates = [
        (float(row["latitude"]), float(row["longitude"]))
        for row in rows
        if is_valid_coordinate(row.get("latitude"), row.get("longitude"))
    ]
    if not coordinates:
        return None

    latitude = sum(item[0] for item in coordinates) / len(coordinates)
    longitude = sum(item[1] for item in coordinates) / len(coordinates)
    source = rows[0].get("source") or {}
    return {
        "latitude": round(latitude, 7),
        "longitude": round(longitude, 7),
        "source": "roadview_image_metadata_centroid",
        "source_title": str(source.get("dataset_name") or "사회적약자 시설 데이터 로드뷰 이미지 메타데이터"),
        "source_url": str(source.get("url") or ""),
        "matched_name": matched_name,
        "match_method": match_method,
        "evidence_count": len(coordinates),
        "point_role": DEFAULT_POINT_ROLE,
    }


def location_from_override(item: Mapping[str, Any]) -> dict[str, Any] | None:
    if not is_valid_coordinate(item.get("latitude"), item.get("longitude")):
        return None
    return {
        "latitude": round(float(item["latitude"]), 7),
        "longitude": round(float(item["longitude"]), 7),
        "source": str(item.get("source") or "manual_override"),
        "source_title": str(item.get("source_title") or "수동 좌표 보강"),
        "source_url": str(item.get("source_url") or ""),
        "matched_name": str(item.get("name") or item.get("spot_id") or ""),
        "match_method": "manual_override",
        "evidence_count": int(item.get("evidence_count") or 1),
        "point_role": normalize_point_role(item.get("point_role")),
    }


def normalize_place_name(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", str(value or "")).lower()


def is_valid_coordinate(latitude: Any, longitude: Any) -> bool:
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    return 32.8 <= lat <= 34.0 and 125.8 <= lng <= 127.2
