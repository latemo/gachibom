"""Shared evidence gate for user-facing travel recommendations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


PUBLIC_RECOMMENDATION_VERIFICATION_STATUSES = frozenset({"verified", "partial"})


def is_grounded_recommendation_candidate(place: Mapping[str, Any]) -> bool:
    """Return whether a place has enough reviewed public evidence to recommend."""

    if str(place.get("status") or "").strip().casefold() != "active":
        return False

    verification = place.get("verification")
    if not isinstance(verification, Mapping):
        return False
    status = str(verification.get("status") or "").strip().casefold()
    if status not in PUBLIC_RECOMMENDATION_VERIFICATION_STATUSES:
        return False

    return any(
        isinstance(source, Mapping) and _is_safe_public_url(source.get("url"))
        for source in (place.get("sources") or [])
    )


def grounded_recommendation_places(
    places: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only places that pass the public recommendation evidence gate."""

    return [place for place in places if is_grounded_recommendation_candidate(place)]


def _is_safe_public_url(value: Any) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)
