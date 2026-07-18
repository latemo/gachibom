"""Build a manual-review queue of Nominatim candidates for unlocated places.

This script deliberately does not update ``place_location_overrides.json``.  A
candidate must be checked by a person against an authoritative source before it
can become a service coordinate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.place_locations import build_place_location_index, is_valid_coordinate


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = (
    "gachibom-jeju-place-location-review/1.0 "
    "(manual candidate review; +https://gachibom.vercel.app/)"
)
MIN_REQUEST_INTERVAL_SECONDS = 1.1
MAX_CANDIDATES = 3

SOURCE = {
    "title": "OpenStreetMap Nominatim Search",
    "url": NOMINATIM_SEARCH_URL,
    "license": "OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0",
    "usage_policy": "https://operations.osmfoundation.org/policies/nominatim/",
}

COMPLETE_STATUSES = frozenset({"candidates_found", "no_candidates"})
SAFE_ADDRESS_FIELDS = (
    "amenity",
    "tourism",
    "building",
    "road",
    "pedestrian",
    "neighbourhood",
    "suburb",
    "borough",
    "city_district",
    "city",
    "town",
    "village",
    "municipality",
    "county",
    "state",
    "ISO3166-2-lvl4",
    "postcode",
    "country",
    "country_code",
)
SAFE_NAME_DETAIL_FIELDS = (
    "name",
    "name:ko",
    "name:en",
    "official_name",
    "official_name:ko",
    "official_name:en",
    "short_name",
    "short_name:ko",
    "short_name:en",
)


def load_json(path: str | Path, *, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping) and isinstance(payload.get("items"), list):
        return [dict(item) for item in payload["items"] if isinstance(item, Mapping)]
    return []


def build_query(place: Mapping[str, Any]) -> str:
    parts = [
        str(place.get("name") or "").strip(),
        str(place.get("region") or "").strip(),
        "제주특별자치도",
        "대한민국",
    ]
    unique_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = "".join(part.split()).casefold()
        if part and normalized not in seen:
            seen.add(normalized)
            unique_parts.append(part)
    return ", ".join(unique_parts)


def find_missing_places(
    places: Iterable[Mapping[str, Any]],
    location_index: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for place in places:
        spot_id = str(place.get("id") or place.get("spot_id") or "").strip()
        name = str(place.get("name") or "").strip()
        if not spot_id or not name or spot_id in seen_ids:
            continue
        seen_ids.add(spot_id)
        if spot_id not in location_index:
            missing.append({"spot_id": spot_id, "name": name, "query": build_query(place)})
    return sorted(missing, key=lambda item: (item["spot_id"], item["name"], item["query"]))


def build_search_url(query: str, *, limit: int = MAX_CANDIDATES) -> str:
    safe_limit = max(1, min(int(limit), MAX_CANDIDATES))
    params = {
        "q": query,
        "format": "jsonv2",
        "countrycodes": "kr",
        "limit": str(safe_limit),
        "addressdetails": "1",
        "namedetails": "1",
        "accept-language": "ko,en",
    }
    return f"{NOMINATIM_SEARCH_URL}?{urlencode(params)}"


def fetch_candidates(
    query: str,
    *,
    user_agent: str,
    limit: int = MAX_CANDIDATES,
    timeout_seconds: float = 30,
    open_url: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    if not user_agent.strip():
        raise ValueError("An identifying User-Agent is required by the Nominatim usage policy.")

    request = Request(
        build_search_url(query, limit=limit),
        headers={"Accept": "application/json", "User-Agent": user_agent.strip()},
    )
    request_opener = open_url or urlopen
    with request_opener(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode(_response_charset(response)))

    if not isinstance(payload, list):
        raise ValueError("Nominatim response must be a JSON list.")

    candidates: list[dict[str, Any]] = []
    for raw_candidate in payload:
        candidate = sanitize_candidate(raw_candidate)
        if candidate is not None:
            candidates.append(candidate)
        if len(candidates) >= max(1, min(int(limit), MAX_CANDIDATES)):
            break
    return candidates


def sanitize_candidate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    latitude = value.get("latitude", value.get("lat"))
    longitude = value.get("longitude", value.get("lon"))
    if not is_valid_coordinate(latitude, longitude):
        return None

    candidate: dict[str, Any] = {
        "latitude": round(float(latitude), 7),
        "longitude": round(float(longitude), 7),
        "display_name": _clean_text(value.get("display_name")),
    }
    _copy_scalar(candidate, "place_id", value.get("place_id"))
    _copy_scalar(candidate, "osm_type", value.get("osm_type"))
    _copy_scalar(candidate, "osm_id", value.get("osm_id"))
    _copy_text(candidate, "name", value.get("name"))
    _copy_text(candidate, "category", value.get("category", value.get("class")))
    _copy_text(candidate, "type", value.get("type"))
    _copy_text(candidate, "address_type", value.get("addresstype"))
    importance = _safe_float(value.get("importance"))
    if importance is not None:
        candidate["importance"] = importance

    address = _safe_text_mapping(value.get("address"), SAFE_ADDRESS_FIELDS)
    if address:
        candidate["address"] = address
    name_details = _safe_text_mapping(value.get("namedetails"), SAFE_NAME_DETAIL_FIELDS)
    if name_details:
        candidate["name_details"] = name_details
    return candidate


def build_candidate_queue(
    places: Sequence[Mapping[str, Any]],
    location_index: Mapping[str, Mapping[str, Any]],
    *,
    existing_output: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    generated_at: str | None = None,
    max_requests: int = 10,
    limit: int = MAX_CANDIDATES,
    user_agent: str = DEFAULT_USER_AGENT,
    request_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
    timeout_seconds: float = 30,
    open_url: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Fetch and checkpoint review candidates for places absent from the index."""

    if max_requests < 0:
        raise ValueError("max_requests must be zero or greater.")
    if request_interval_seconds < MIN_REQUEST_INTERVAL_SECONDS:
        raise ValueError(
            f"request_interval_seconds must be at least {MIN_REQUEST_INTERVAL_SECONDS}."
        )
    if not user_agent.strip():
        raise ValueError("An identifying User-Agent is required.")

    missing = find_missing_places(places, location_index)
    cache = _cache_index(existing_output)
    items: list[dict[str, Any]] = []
    cached_results = 0
    for missing_item in missing:
        cached = cache.get((missing_item["spot_id"], missing_item["query"]))
        if cached is None:
            item = {**missing_item, "status": "pending", "candidates": []}
        else:
            candidates = [
                candidate
                for value in cached.get("candidates", [])
                if (candidate := sanitize_candidate(value)) is not None
            ][: max(1, min(int(limit), MAX_CANDIDATES))]
            status = "candidates_found" if candidates else "no_candidates"
            item = {**missing_item, "status": status, "candidates": candidates}
            cached_results += 1
        items.append(item)

    requests_this_run = 0

    def document() -> dict[str, Any]:
        return _build_document(
            places=places,
            location_index=location_index,
            items=items,
            generated_at=generated_at or date.today().isoformat(),
            requests_this_run=requests_this_run,
            cached_results=cached_results,
        )

    for item in items:
        if requests_this_run >= max_requests:
            break
        if item["status"] != "pending":
            continue
        if requests_this_run:
            (sleep_fn or sleep)(request_interval_seconds)
        try:
            candidates = fetch_candidates(
                item["query"],
                user_agent=user_agent,
                limit=limit,
                timeout_seconds=timeout_seconds,
                open_url=open_url,
            )
        except Exception:
            item["status"] = "request_error"
            item["candidates"] = []
        else:
            item["status"] = "candidates_found" if candidates else "no_candidates"
            item["candidates"] = candidates
        requests_this_run += 1
        if output_path is not None:
            atomic_write_json(output_path, document())

    result = document()
    if output_path is not None and requests_this_run == 0:
        atomic_write_json(output_path, result)
    return result


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, target)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--places",
        type=Path,
        default=Path("data/jeju_accessible_spots.json"),
        help="Accessibility place cards JSON.",
    )
    parser.add_argument(
        "--roadview-metadata",
        type=Path,
        default=Path("data/roadview_image_metadata.json"),
        help="Roadview coordinate metadata JSON.",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=Path("data/place_location_overrides.json"),
        help="Existing reviewed location overrides (read-only).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/place_location_candidates.json"),
        help="Manual-review candidate queue JSON.",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=10,
        help="Maximum new Nominatim requests in this run; cached items do not count.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        choices=range(1, MAX_CANDIDATES + 1),
        default=MAX_CANDIDATES,
        metavar="{1,2,3}",
        help="Maximum candidates requested per place.",
    )
    parser.add_argument("--generated-at", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Identifying User-Agent.")
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=MIN_REQUEST_INTERVAL_SECONDS,
        help="Delay between requests; must be at least 1.1 seconds.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_requests < 0:
        raise SystemExit("--max-requests must be zero or greater")
    if args.request_interval_seconds < MIN_REQUEST_INTERVAL_SECONDS:
        raise SystemExit("--request-interval-seconds must be at least 1.1")

    places = extract_items(load_json(args.places, default=[]))
    roadview_metadata = extract_items(load_json(args.roadview_metadata, default=[]))
    overrides = extract_items(load_json(args.overrides, default=[]))
    location_index = build_place_location_index(
        places,
        roadview_metadata=roadview_metadata,
        overrides=overrides,
    )
    existing_output = load_json(args.output, default={})
    result = build_candidate_queue(
        places,
        location_index,
        existing_output=existing_output if isinstance(existing_output, Mapping) else {},
        output_path=args.output,
        generated_at=args.generated_at,
        max_requests=args.max_requests,
        limit=args.limit,
        user_agent=args.user_agent,
        request_interval_seconds=args.request_interval_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    summary = result["summary"]
    print(f"place_location_candidates_output={args.output}")
    print(
        "summary="
        f"missing:{summary['missing_locations']}, "
        f"candidates:{summary['candidates_found']}, "
        f"pending:{summary['pending']}, "
        f"requests:{summary['requests_this_run']}"
    )
    return 0


def _build_document(
    *,
    places: Sequence[Mapping[str, Any]],
    location_index: Mapping[str, Mapping[str, Any]],
    items: list[dict[str, Any]],
    generated_at: str,
    requests_this_run: int,
    cached_results: int,
) -> dict[str, Any]:
    statuses = [item["status"] for item in items]
    place_ids = {
        str(place.get("id") or place.get("spot_id") or "").strip()
        for place in places
        if str(place.get("id") or place.get("spot_id") or "").strip()
    }
    return {
        "source": dict(SOURCE),
        "generated_at": generated_at,
        "review_policy": {
            "automatic_override_promotion": False,
            "required_decision": "manual_review",
        },
        "summary": {
            "total_places": len(place_ids),
            "already_located": len(place_ids.intersection(location_index)),
            "missing_locations": len(items),
            "cached_results": cached_results,
            "requests_this_run": requests_this_run,
            "candidates_found": statuses.count("candidates_found"),
            "no_candidates": statuses.count("no_candidates"),
            "request_errors": statuses.count("request_error"),
            "pending": statuses.count("pending"),
        },
        "items": items,
    }


def _cache_index(existing_output: Mapping[str, Any] | None) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    if not isinstance(existing_output, Mapping):
        return result
    for item in existing_output.get("items", []):
        if not isinstance(item, Mapping) or item.get("status") not in COMPLETE_STATUSES:
            continue
        spot_id = str(item.get("spot_id") or "").strip()
        query = str(item.get("query") or "").strip()
        candidates = item.get("candidates")
        if spot_id and query and isinstance(candidates, list):
            result[(spot_id, query)] = item
    return result


def _response_charset(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if headers is not None and hasattr(headers, "get_content_charset"):
        return headers.get_content_charset() or "utf-8"
    return "utf-8"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _copy_text(target: dict[str, Any], key: str, value: Any) -> None:
    text = _clean_text(value)
    if text:
        target[key] = text


def _copy_scalar(target: dict[str, Any], key: str, value: Any) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        target[key] = value
        return
    text = _clean_text(value)
    if text:
        target[key] = text


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _safe_text_mapping(value: Any, allowed_fields: Sequence[str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key in allowed_fields:
        text = _clean_text(value.get(key))
        if text:
            result[key] = text
    return result


if __name__ == "__main__":
    raise SystemExit(main())
