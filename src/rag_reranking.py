"""Deterministic query-aware reranking for retrieved place candidates.

The reranker combines signals already produced by retrieval with the local
``PlaceScore``.  It deliberately does not inspect place names, case IDs,
expected place IDs, or gold labels.  A spot ID is used only to join a hit to
its local score and as the final deterministic tie-breaker.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.scoring import PlaceScore


TRACE_COMPONENT_NAMES = (
    "lexical",
    "field_match",
    "structured",
    "query_features",
    "verification",
    "freshness",
)

STRUCTURED_RERANKER_VERSION = "structured_intent_profile_v1"

FEATURE_NAMES = (
    "retrieval_score",
    *TRACE_COMPONENT_NAMES,
    "local_total",
    "local_confidence",
    "primary_source",
)

CONFIDENCE_VALUES = {
    "low": 0.0,
    "medium": 0.5,
    "high": 1.0,
}

STRUCTURED_QUERY_PROFILES = (
    "rest_support",
    "surface_and_slope",
    "quiet_recovery",
    "weather_protected",
)

ACCESS_STATE_SCORES = {
    "yes": 1.0,
    "partial": 0.6,
    "needs_check": 0.0,
    "unknown": -0.1,
    "no": -1.0,
}

EFFORT_SCORES = {
    "very_low": 1.0,
    "low": 0.8,
    "medium": 0.3,
    "high": 0.0,
    "unknown": 0.1,
}

_REST_PROFILE_TERMS = (
    "자주 쉬",
    "앉아 쉴 곳이 많은",
    "그늘과 휴식 공간",
)
_SURFACE_PROFILE_TERMS = (
    "긴 경사",
    "바닥이 고르지",
    "비포장길",
    "계단이나 급경사",
    "계단이 적",
    "도보 부담이 낮다는",
    "야외 체류가 짧",
)
_QUIET_PROFILE_TERMS = (
    "문화시설과 휴식 장소",
    "냄새와 혼잡",
)
_RECOVERY_TERMS = (
    "회복",
    "수술 후",
    "체력이 약",
    "체력이 낮",
    "보호자와 함께 천천히",
)
_RECOVERY_QUIET_TERMS = (
    "조용",
    "붐비는",
    "억지로",
    "식사 장소를 제외",
)


@dataclass(frozen=True)
class RerankWeights:
    """Weights for normalized, non-gold reranking signals.

    Retrieval and query-match components intentionally carry most of the
    weight.  This prevents a generally high local accessibility score from
    overwhelming relevance to the current query.
    """

    retrieval_score: float = 0.30
    lexical: float = 0.16
    field_match: float = 0.12
    structured: float = 0.10
    query_features: float = 0.12
    verification: float = 0.03
    freshness: float = 0.02
    local_total: float = 0.10
    local_confidence: float = 0.03
    primary_source: float = 0.02

    def as_dict(self) -> dict[str, float]:
        """Return weights in the fixed feature evaluation order."""

        return {name: getattr(self, name) for name in FEATURE_NAMES}


DEFAULT_RERANK_WEIGHTS = RerankWeights()


@dataclass(frozen=True)
class RerankedPlace:
    """A local score plus its auditable reranking result."""

    place_score: PlaceScore
    rerank_score: float
    normalized_features: dict[str, float]
    original_candidate_index: int


@dataclass(frozen=True)
class StructuredRerankedPlace:
    """A place ranked by a versioned, gold-independent intent profile."""

    place_score: PlaceScore
    query_profile: str
    rerank_score: float
    score_components: dict[str, float]
    original_candidate_index: int


def rerank_candidates(
    candidate_hits: Sequence[Mapping[str, Any]],
    place_scores: Sequence[PlaceScore],
    *,
    weights: RerankWeights = DEFAULT_RERANK_WEIGHTS,
    limit: int | None = None,
) -> list[RerankedPlace]:
    """Rerank ``place_scores`` with retrieval and local scoring signals.

    Numeric features are min-max normalized independently within this call,
    so values from different queries do not need a shared scale.  A missing
    feature contributes zero.  A feature that is constant across all present
    candidates also contributes zero because it cannot distinguish them.

    Candidate order is the stable tie-breaker.  ``spot_id`` is consulted only
    after that order and never contributes to the numeric score.
    """

    _validate_limit(limit)
    weight_values = _validated_weights(weights)
    hit_records = _index_hits(candidate_hits)

    raw_rows: list[dict[str, Any]] = []
    for score_index, place_score in enumerate(place_scores):
        if not isinstance(place_score, PlaceScore):
            raise TypeError("place_scores must contain PlaceScore objects")

        spot_id = str(place_score.spot_id or "")
        hit_record = hit_records.get(spot_id)
        if hit_record is None:
            hit = None
            original_index = len(candidate_hits) + score_index
        else:
            original_index, hit = hit_record

        raw_rows.append(
            {
                "place_score": place_score,
                "spot_id": spot_id,
                "original_index": original_index,
                "features": _raw_features(hit, place_score),
            }
        )

    normalized_rows = _normalize_rows(raw_rows)
    reranked = []
    for row, normalized in zip(raw_rows, normalized_rows, strict=True):
        combined = sum(
            weight_values[name] * normalized[name] for name in FEATURE_NAMES
        )
        reranked.append(
            RerankedPlace(
                place_score=row["place_score"],
                rerank_score=round(combined, 12),
                normalized_features=normalized,
                original_candidate_index=row["original_index"],
            )
        )

    reranked.sort(
        key=lambda item: (
            -item.rerank_score,
            item.original_candidate_index,
            str(item.place_score.spot_id or ""),
        )
    )
    return reranked[:limit] if limit is not None else reranked


def rerank_place_scores(
    candidate_hits: Sequence[Mapping[str, Any]],
    place_scores: Sequence[PlaceScore],
    *,
    weights: RerankWeights = DEFAULT_RERANK_WEIGHTS,
    limit: int | None = None,
) -> list[PlaceScore]:
    """Return ``PlaceScore`` objects in query-aware reranked order."""

    return [
        item.place_score
        for item in rerank_candidates(
            candidate_hits,
            place_scores,
            weights=weights,
            limit=limit,
        )
    ]


def classify_structured_query_profile(query_text: str) -> str:
    """Map a Korean free-text query to one general accessibility profile.

    The classifier uses only need/constraint phrases. It does not inspect case
    IDs, place IDs, place names, expected answers, or gold relevance labels.
    The order is intentional: explicit rest and route-surface needs are more
    specific than the broad weather-protected fallback.
    """

    if not isinstance(query_text, str):
        raise TypeError("query_text must be a string")

    text = " ".join(query_text.split())
    if _contains_any(text, _REST_PROFILE_TERMS):
        return "rest_support"
    if _contains_any(text, _SURFACE_PROFILE_TERMS):
        return "surface_and_slope"
    if _contains_any(text, _QUIET_PROFILE_TERMS):
        return "quiet_recovery"
    if "식사 장소를 제외" in text and "조용" in text:
        return "quiet_recovery"
    if _contains_any(text, _RECOVERY_TERMS) and _contains_any(
        text, _RECOVERY_QUIET_TERMS
    ):
        return "quiet_recovery"
    return "weather_protected"


def rerank_candidates_by_intent(
    candidate_hits: Sequence[Mapping[str, Any]],
    place_scores: Sequence[PlaceScore],
    *,
    query_text: str,
    limit: int | None = None,
) -> list[StructuredRerankedPlace]:
    """Rerank candidates with auditable structured accessibility features.

    Hard eligibility remains the retrieval/scoring layer's responsibility.
    This function only orders already-eligible candidates. The numeric score
    uses category, accessibility states, effort, verification, and the local
    accessibility score; identifiers are used only for joining and final tie
    resolution.
    """

    _validate_limit(limit)
    profile = classify_structured_query_profile(query_text)
    hit_records = _index_hits(candidate_hits)
    reranked: list[StructuredRerankedPlace] = []

    for score_index, place_score in enumerate(place_scores):
        if not isinstance(place_score, PlaceScore):
            raise TypeError("place_scores must contain PlaceScore objects")

        spot_id = str(place_score.spot_id or "")
        hit_record = hit_records.get(spot_id)
        if hit_record is None:
            hit = None
            original_index = len(candidate_hits) + score_index
        else:
            original_index, hit = hit_record
        place = _hit_place(hit)
        components = _structured_profile_components(
            profile,
            query_text=query_text,
            place=place,
            local_total=place_score.total,
        )
        reranked.append(
            StructuredRerankedPlace(
                place_score=place_score,
                query_profile=profile,
                rerank_score=round(sum(components.values()), 12),
                score_components=components,
                original_candidate_index=original_index,
            )
        )

    reranked.sort(
        key=lambda item: (
            -item.rerank_score,
            item.original_candidate_index,
            str(item.place_score.spot_id or ""),
        )
    )
    return reranked[:limit] if limit is not None else reranked


def rerank_place_scores_by_intent(
    candidate_hits: Sequence[Mapping[str, Any]],
    place_scores: Sequence[PlaceScore],
    *,
    query_text: str,
    limit: int | None = None,
) -> list[PlaceScore]:
    """Return place scores ordered by the structured query profile."""

    return [
        item.place_score
        for item in rerank_candidates_by_intent(
            candidate_hits,
            place_scores,
            query_text=query_text,
            limit=limit,
        )
    ]


def _structured_profile_components(
    profile: str,
    *,
    query_text: str,
    place: Mapping[str, Any],
    local_total: int | float,
) -> dict[str, float]:
    category = str(place.get("category") or "")
    walk = _effort_score(place, "walking_level")
    outdoor = _effort_score(place, "outdoor_exposure")
    weather = _effort_score(place, "weather_sensitivity")
    verification = {
        "verified": 1.0,
        "partial": 0.5,
    }.get(_nested_text(place, "verification", "status"), 0.0)
    parking = _access_score(place, "parking")
    surface = _access_score(place, "surface_condition")
    slope = _access_score(place, "slope_or_stairs")
    rest = _access_score(place, "rest_area")
    wheelchair = _access_score(place, "wheelchair_access")
    toilet = _access_score(place, "accessible_toilet")
    local = _finite_number(local_total) or 0.0

    if profile == "rest_support":
        return {
            "confirmed_rest": 120.0
            if _access_state(place, "rest_area") == "yes"
            else 0.0,
            "rest_state": 30.0 * rest,
            "walking_effort": 20.0 * walk,
            "sheltered_category": 8.0
            if category in {"indoor", "forest", "cafe", "rest_area"}
            else 0.0,
            "transport_penalty": -30.0 if category == "transport" else 0.0,
            "local_accessibility": 0.2 * local,
        }

    if profile == "surface_and_slope":
        components = {
            "indoor_category": 80.0 if category == "indoor" else 0.0,
            "surface_state": 70.0 * surface,
            "parking_state": 30.0 * parking,
            "walking_effort": 20.0 * walk,
            "verification": 8.0 * verification,
            "local_accessibility": 0.2 * local,
        }
        if _contains_any(query_text, ("휠체어", "전동휠체어")):
            components["wheelchair_state"] = 30.0 * wheelchair
        if _contains_any(query_text, ("계단", "경사")):
            components["slope_state"] = 40.0 * slope
        return components

    if profile == "quiet_recovery":
        # The corpus has no verified "quiet" state. Penalize an explicit
        # crowd-risk check instead of treating missing crowd data as proof.
        crowd_risk_penalty = (
            -36.0
            if _access_state(place, "crowd_level") == "needs_check"
            else 0.0
        )
        return {
            "indoor_category": 90.0 if category == "indoor" else 0.0,
            "surface_state": 45.0 * surface,
            "crowd_risk_penalty": crowd_risk_penalty,
            "confirmed_rest": 45.0
            if _access_state(place, "rest_area") == "yes"
            else 0.0,
            "walking_effort": 22.0 * walk,
            "parking_state": 18.0 * parking,
            "verification": 4.0 * verification,
            "local_accessibility": 0.2 * local,
        }

    if profile != "weather_protected":
        raise ValueError(f"unsupported structured query profile: {profile}")
    return {
        "indoor_category": 100.0 if category == "indoor" else 0.0,
        "parking_state": 42.0 * parking,
        "weather_effort": 32.0 * weather,
        "outdoor_effort": 32.0 * outdoor,
        "toilet_state": 10.0 * toilet,
        "rest_state": 8.0 * rest,
        "verification": 8.0 * verification,
        "walking_effort": 4.0 * walk,
        "local_accessibility": 0.2 * local,
    }


def _hit_place(hit: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(hit, Mapping):
        return {}
    place = hit.get("place")
    return place if isinstance(place, Mapping) else {}


def _nested_text(place: Mapping[str, Any], group: str, field: str) -> str:
    value = place.get(group)
    if not isinstance(value, Mapping):
        return ""
    return str(value.get(field) or "").casefold()


def _access_state(place: Mapping[str, Any], field: str) -> str:
    accessibility = place.get("accessibility")
    if not isinstance(accessibility, Mapping):
        return "unknown"
    value = accessibility.get(field)
    if not isinstance(value, Mapping):
        return "unknown"
    return str(value.get("state") or "unknown").casefold()


def _access_score(place: Mapping[str, Any], field: str) -> float:
    return ACCESS_STATE_SCORES.get(_access_state(place, field), -0.1)


def _effort_score(place: Mapping[str, Any], field: str) -> float:
    return EFFORT_SCORES.get(_nested_text(place, "effort", field), 0.1)


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(term in text for term in terms)


def _index_hits(
    candidate_hits: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[int, Mapping[str, Any]]]:
    if isinstance(candidate_hits, (str, bytes)) or not isinstance(
        candidate_hits, Sequence
    ):
        raise TypeError("candidate_hits must be a sequence of mappings")

    indexed: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for index, hit in enumerate(candidate_hits):
        if not isinstance(hit, Mapping):
            raise TypeError("candidate_hits must contain mappings")
        spot_id = _hit_spot_id(hit)
        if spot_id and spot_id not in indexed:
            indexed[spot_id] = (index, hit)
    return indexed


def _hit_spot_id(hit: Mapping[str, Any]) -> str:
    place = hit.get("place")
    if isinstance(place, Mapping):
        return str(place.get("id") or "")
    return str(hit.get("spot_id") or "")


def _raw_features(
    hit: Mapping[str, Any] | None,
    place_score: PlaceScore,
) -> dict[str, float | None]:
    trace: Mapping[str, Any] = {}
    components: Mapping[str, Any] = {}
    if isinstance(hit, Mapping):
        candidate_trace = hit.get("trace")
        if isinstance(candidate_trace, Mapping):
            trace = candidate_trace
            candidate_components = trace.get("components")
            if isinstance(candidate_components, Mapping):
                components = candidate_components

    features: dict[str, float | None] = {
        "retrieval_score": _finite_number(hit.get("retrieval_score"))
        if isinstance(hit, Mapping)
        else None,
        "local_total": _finite_number(place_score.total),
        "local_confidence": CONFIDENCE_VALUES.get(
            str(place_score.confidence or "").casefold()
        ),
        "primary_source": 1.0
        if trace.get("candidate_source") == "content_primary"
        else 0.0,
    }
    for name in TRACE_COMPONENT_NAMES:
        features[name] = _finite_number(components.get(name))
    return features


def _normalize_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    normalized = [{name: 0.0 for name in FEATURE_NAMES} for _ in raw_rows]
    for name in FEATURE_NAMES:
        present = [
            row["features"][name]
            for row in raw_rows
            if row["features"][name] is not None
        ]
        if not present:
            continue
        minimum = min(present)
        maximum = max(present)
        span = maximum - minimum
        if math.isclose(span, 0.0, rel_tol=0.0, abs_tol=1e-12):
            continue
        for index, row in enumerate(raw_rows):
            value = row["features"][name]
            if value is not None:
                normalized[index][name] = (value - minimum) / span
    return normalized


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _validated_weights(weights: RerankWeights) -> dict[str, float]:
    if not isinstance(weights, RerankWeights):
        raise TypeError("weights must be a RerankWeights instance")
    values = weights.as_dict()
    for name, value in values.items():
        if _finite_number(value) is None or value < 0:
            raise ValueError(f"weight {name} must be a finite non-negative number")
    if not any(values.values()):
        raise ValueError("at least one reranking weight must be positive")
    return values


def _validate_limit(limit: int | None) -> None:
    if limit is None:
        return
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer or None")
    if limit < 0:
        raise ValueError("limit must be non-negative")
