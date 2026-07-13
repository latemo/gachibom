"""Deterministic visit-order optimization for short recommendation routes."""

from __future__ import annotations

from itertools import permutations
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any, Mapping, Sequence


EARTH_RADIUS_KM = 6371.0
MAX_OPTIMIZED_STOPS = 4


def optimize_course_route(
    route: Sequence[Mapping[str, Any]],
    location_index: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return the same stops in the shortest coordinate-based open-path order.

    Recommendation routes contain at most four stops, so checking every
    permutation is both exact and inexpensive. If any stop lacks a usable
    coordinate, the original order is retained rather than presenting a
    partially optimized route as complete.
    """

    copied_route = [dict(item) for item in route]
    if len(copied_route) < 3 or len(copied_route) > MAX_OPTIMIZED_STOPS:
        return _renumber(copied_route)

    coordinates = [
        _coordinate_for(item.get("spot_id"), location_index)
        for item in copied_route
    ]
    if any(coordinate is None for coordinate in coordinates):
        return _renumber(copied_route)

    resolved_coordinates = [
        coordinate for coordinate in coordinates if coordinate is not None
    ]
    original_indexes = tuple(range(len(copied_route)))
    best_indexes = min(
        permutations(original_indexes),
        key=lambda indexes: (
            round(_path_distance_km(indexes, resolved_coordinates), 12),
            indexes,
        ),
    )
    return _renumber([copied_route[index] for index in best_indexes])


def _coordinate_for(
    spot_id: Any,
    location_index: Mapping[str, Mapping[str, Any]],
) -> tuple[float, float] | None:
    location = location_index.get(str(spot_id or ""))
    if not isinstance(location, Mapping):
        return None
    latitude = _finite_float(location.get("latitude"))
    longitude = _finite_float(location.get("longitude"))
    if latitude is None or longitude is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _path_distance_km(
    indexes: Sequence[int],
    coordinates: Sequence[tuple[float, float]],
) -> float:
    return sum(
        _haversine_km(coordinates[left], coordinates[right])
        for left, right in zip(indexes, indexes[1:])
    )


def _haversine_km(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    start_latitude, start_longitude = start
    end_latitude, end_longitude = end
    latitude_delta = radians(end_latitude - start_latitude)
    longitude_delta = radians(end_longitude - start_longitude)
    start_latitude_radians = radians(start_latitude)
    end_latitude_radians = radians(end_latitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(start_latitude_radians)
        * cos(end_latitude_radians)
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(min(1.0, sqrt(haversine)))


def _renumber(route: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**item, "order": index}
        for index, item in enumerate(route, start=1)
    ]
