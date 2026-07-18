"""Deterministic retrieval for grounded Jeju accessibility recommendations.

The module deliberately has no LLM or vector-database dependency.  It narrows
the reviewed place-card corpus with structured constraints, ranks the remaining
cards with a small BM25 implementation, and returns bounded evidence that can be
passed to a later generation step.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import date
from typing import Any
from urllib.parse import urlsplit


DEFAULT_LIMIT = 12
MAX_LIMIT = 50
BM25_K1 = 1.5
BM25_B = 0.75
EVIDENCE_NOTE_MAX_LENGTH = 320

ACTIVE_STATUSES = {"active"}
CLOSED_SERVICE_STATUSES = {"permanently_closed", "temporarily_closed"}
VERIFICATION_RANK = {
    "unavailable": 0,
    "needs_check": 1,
    "partial": 2,
    "verified": 3,
}
VERIFICATION_SCORE = {
    "verified": 2.5,
    "partial": 1.0,
    "needs_check": -1.5,
    "unavailable": -6.0,
}
ACCESSIBILITY_STATES = {"yes", "partial", "needs_check", "unknown", "no"}
SAFE_REQUIRED_ACCESSIBILITY_STATES = {"yes", "partial"}
EFFORT_RANK = {"very_low": 0, "low": 1, "medium": 2, "high": 3}
STEP_FREE_EVIDENCE_TERMS = (
    "계단 없음",
    "계단이 없음",
    "단차 없음",
    "단차가 없음",
    "무단차",
    "턱이 없",
    "엘리베이터",
    "승강기",
)
FLAT_ROUTE_EVIDENCE_TERMS = (
    "경사 없음",
    "경사가 없음",
    "단차 없음",
    "단차가 없음",
    "무단차",
    "평탄",
    "턱이 없",
)

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
KOREAN_SUFFIXES = (
    "에서",
    "에게",
    "으로",
    "이랑",
    "랑",
    "과",
    "와",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "의",
    "에",
    "도",
    "만",
    "로",
)

CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "cafe": ("카페", "차", "디저트"),
    "culture": ("문화", "예술", "역사", "기념관"),
    "food_market": ("시장", "먹거리", "전통시장"),
    "forest": ("숲", "숲길", "자연휴양림", "산책"),
    "indoor": ("실내", "박물관", "전시관", "문학관", "기념관", "센터"),
    "medical_support": ("의료", "병원", "보건", "약국"),
    "oreum": ("오름", "산", "등산"),
    "other": ("기타",),
    "rest_area": ("휴식", "휴게", "공원", "쉼터"),
    "restaurant": ("식당", "음식점", "맛집"),
    "sea": ("바다", "해안", "해수욕장", "포구"),
    "shopping": ("쇼핑", "매장", "기념품"),
    "transport": ("교통", "터미널", "공항", "항만"),
}

ACCESSIBILITY_ALIASES: dict[str, tuple[str, ...]] = {
    "wheelchair_access": (
        "휠체어",
        "휠체어 접근",
        "전동휠체어",
        "무장애",
        "전동스쿠터",
        "보장구",
    ),
    "accessible_toilet": ("장애인화장실", "화장실"),
    "parking": ("장애인주차", "전용주차", "주차"),
    "slope_or_stairs": ("경사", "경사로", "계단", "단차", "승강기", "엘리베이터"),
    "rest_area": ("휴식", "휴식 공간", "휴게", "쉼터", "쉼팡", "좌석"),
    "rental_or_assistance": ("대여", "보조", "도움", "유아차", "휠체어대여"),
    "surface_condition": ("바닥", "노면", "포장", "데크", "요철"),
    "crowd_level": ("혼잡", "대기", "붐빔"),
}

INTENT_KEYS = {
    "region",
    "regions",
    "category",
    "categories",
    "exclude_categories",
    "accessibility",
    "required_accessibility",
    "min_verification",
    "verified_only",
    "require_all_accessibility_verified",
    "require_24_hours",
    "require_night_hours",
    "max_weather_sensitivity",
    "max_outdoor_exposure",
    "max_walking_level",
    "require_step_free",
    "require_flat_route",
    "exclude_warning_terms",
}


def retrieve_place_candidates(
    places: Iterable[Mapping[str, Any]],
    *,
    query: str = "",
    intent: Mapping[str, Any] | None = None,
    limit: int = DEFAULT_LIMIT,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Return ranked place copies with retrieval evidence and a safe trace.

    ``region``/``regions`` and ``category``/``categories`` in ``intent`` are
    hard filters. ``required_accessibility`` accepts field names or Korean
    labels and requires a ``yes`` or ``partial`` state. ``accessibility`` may
    instead be a mapping of field names to explicitly allowed states.

    The trace reports counts and component scores only.  It never contains the
    raw query, query tokens, or raw intent values.
    """

    _validate_limit(limit)
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if intent is not None and not isinstance(intent, Mapping):
        raise TypeError("intent must be a mapping or None")
    if as_of is not None and not isinstance(as_of, date):
        raise TypeError("as_of must be a date or None")

    rows = _validate_places(places)
    normalized_intent = _normalize_intent(intent or {})
    eligible = [place for place in rows if _passes_filters(place, normalized_intent)]
    if not eligible:
        return []

    query_tokens = _tokenize(query)
    query_counter = Counter(query_tokens)
    document_tokens = [_document_tokens(place) for place in eligible]
    lexical_scores, matched_counts = _bm25_scores(document_tokens, query_counter)
    effective_date = as_of or date.today()
    query_accessibility = _query_accessibility_fields(query)
    query_categories = _query_categories(query)
    filters_applied = _filter_trace(normalized_intent)

    ranked: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for place, lexical_score, matched_count in zip(
        eligible, lexical_scores, matched_counts, strict=True
    ):
        reasons: list[str] = []
        substring_score = _substring_score(place, query_tokens, reasons)
        structured_score = _structured_score(place, normalized_intent, reasons)
        query_feature_score = _query_feature_score(
            place,
            query_accessibility=query_accessibility,
            query_categories=query_categories,
            reasons=reasons,
        )
        content_relevance = (
            lexical_score
            + substring_score
            + structured_score
            + max(0.0, query_feature_score)
        )
        if query_tokens and content_relevance <= 0:
            continue
        verification_score, freshness_score, freshness = _trust_scores(
            place, as_of=effective_date, reasons=reasons
        )
        total = (
            lexical_score
            + substring_score
            + structured_score
            + query_feature_score
            + verification_score
            + freshness_score
        )
        rounded_components = {
            "lexical": round(lexical_score, 6),
            "field_match": round(substring_score, 6),
            "structured": round(structured_score, 6),
            "query_features": round(query_feature_score, 6),
            "verification": round(verification_score, 6),
            "freshness": round(freshness_score, 6),
        }
        result = {
            "place": deepcopy(dict(place)),
            "retrieval_score": round(total, 6),
            "retrieval_reasons": _unique(reasons) or ["검증 상태와 최신성을 기준으로 후보를 정렬"],
            "evidence_bundle": _evidence_bundle(place, freshness=freshness),
            "trace": {
                "retriever": "deterministic_bm25_structured_v1",
                "query_term_count": len(query_tokens),
                "matched_query_term_count": matched_count,
                "query_feature_count": len(query_accessibility) + len(query_categories),
                "intent_field_count": len(normalized_intent["intent_fields"]),
                "filters_applied": filters_applied,
                "components": rounded_components,
            },
        }
        verification_status = _verification_status(place)
        sort_key = (
            -round(total, 12),
            -round(lexical_score + substring_score + query_feature_score, 12),
            -VERIFICATION_RANK.get(verification_status, -1),
            _normalized_text(place.get("name")),
            str(place.get("id") or ""),
            _stable_place_digest(place),
        )
        ranked.append((sort_key, result))

    ranked.sort(key=lambda item: item[0])
    return [result for _, result in ranked[:limit]]


def _validate_limit(limit: Any) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")


def _validate_places(places: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(places, (str, bytes, Mapping)) or not isinstance(places, Iterable):
        raise TypeError("places must be an iterable of mappings")
    rows = list(places)
    for index, place in enumerate(rows):
        if not isinstance(place, Mapping):
            raise TypeError(f"places[{index}] must be a mapping")
    return rows


def _normalize_intent(intent: Mapping[str, Any]) -> dict[str, Any]:
    regions = {_normalized_text(value) for value in _string_values(intent.get("regions", intent.get("region")))}
    regions.discard("")
    categories = {
        category
        for value in _string_values(intent.get("categories", intent.get("category")))
        if (category := _canonical_category(value))
    }
    excluded_categories = {
        category
        for value in _string_values(intent.get("exclude_categories"))
        if (category := _canonical_category(value))
    }
    accessibility = _normalize_accessibility_requirements(intent)
    min_verification = _canonical_verification(intent.get("min_verification"))
    if intent.get("verified_only") is True:
        min_verification = "verified"

    max_weather_sensitivity = _canonical_effort_level(intent.get("max_weather_sensitivity"))
    max_outdoor_exposure = _canonical_effort_level(intent.get("max_outdoor_exposure"))
    max_walking_level = _canonical_effort_level(intent.get("max_walking_level"))
    excluded_warning_terms = {
        str(value).strip().casefold()
        for value in _string_values(intent.get("exclude_warning_terms"))
        if str(value).strip()
    }

    present_fields = sorted(
        key for key in INTENT_KEYS if key in intent and _has_intent_value(intent.get(key))
    )
    return {
        "regions": regions,
        "categories": categories,
        "excluded_categories": excluded_categories,
        "accessibility": accessibility,
        "min_verification": min_verification,
        "require_all_accessibility_verified": intent.get("require_all_accessibility_verified") is True,
        "require_24_hours": intent.get("require_24_hours") is True,
        "require_night_hours": intent.get("require_night_hours") is True,
        "max_weather_sensitivity": max_weather_sensitivity,
        "max_outdoor_exposure": max_outdoor_exposure,
        "max_walking_level": max_walking_level,
        "require_step_free": intent.get("require_step_free") is True,
        "require_flat_route": intent.get("require_flat_route") is True,
        "excluded_warning_terms": excluded_warning_terms,
        "intent_fields": present_fields,
    }


def _normalize_accessibility_requirements(intent: Mapping[str, Any]) -> dict[str, set[str]]:
    requirements: dict[str, set[str]] = {}
    for value in _string_values(intent.get("required_accessibility")):
        field = _canonical_accessibility_field(value)
        if field:
            requirements[field] = set(SAFE_REQUIRED_ACCESSIBILITY_STATES)

    raw = intent.get("accessibility")
    if isinstance(raw, Mapping):
        for raw_field, raw_states in raw.items():
            field = _canonical_accessibility_field(raw_field)
            if not field:
                continue
            if raw_states is False:
                continue
            states = {
                state
                for value in _string_values(raw_states)
                if (state := _canonical_accessibility_state(value))
            }
            if isinstance(raw_states, bool):
                states = set(SAFE_REQUIRED_ACCESSIBILITY_STATES) if raw_states else set()
            requirements[field] = states or set(SAFE_REQUIRED_ACCESSIBILITY_STATES)
    else:
        for value in _string_values(raw):
            field = _canonical_accessibility_field(value)
            if field:
                requirements[field] = set(SAFE_REQUIRED_ACCESSIBILITY_STATES)
    return requirements


def _passes_filters(place: Mapping[str, Any], intent: Mapping[str, Any]) -> bool:
    if str(place.get("status") or "").casefold() not in ACTIVE_STATUSES:
        return False
    visit_info = place.get("visit_info")
    if isinstance(visit_info, Mapping) and visit_info.get("service_status") in CLOSED_SERVICE_STATUSES:
        return False
    if _verification_status(place) == "unavailable":
        return False

    categories = intent["categories"]
    place_category = str(place.get("category") or "").casefold()
    if categories and place_category not in categories:
        return False
    if place_category in intent["excluded_categories"]:
        return False

    warning_text = " ".join(
        str(value).casefold()
        for value in (*_string_values(place.get("avoid_for")), *_string_values(place.get("safety_notes")))
    )
    if any(term in warning_text for term in intent["excluded_warning_terms"]):
        return False

    regions = intent["regions"]
    if regions and not any(_region_matches(place.get("region"), region) for region in regions):
        return False

    minimum = intent["min_verification"]
    if minimum and VERIFICATION_RANK.get(_verification_status(place), -1) < VERIFICATION_RANK[minimum]:
        return False

    effort = place.get("effort")
    effort = effort if isinstance(effort, Mapping) else {}
    for field in ("weather_sensitivity", "outdoor_exposure", "walking_level"):
        maximum = intent[f"max_{field}"]
        if maximum and not _effort_at_most(effort.get(field), maximum):
            return False

    visit_info = place.get("visit_info")
    visit_info = visit_info if isinstance(visit_info, Mapping) else {}
    if intent["require_24_hours"] and not _has_operating_hours_evidence(visit_info, require_24_hours=True):
        return False
    if intent["require_night_hours"] and not _has_operating_hours_evidence(visit_info, require_night=True):
        return False

    accessibility = place.get("accessibility")
    accessibility = accessibility if isinstance(accessibility, Mapping) else {}
    for field, allowed_states in intent["accessibility"].items():
        value = accessibility.get(field)
        state = str(value.get("state") if isinstance(value, Mapping) else "unknown").casefold()
        if state not in allowed_states:
            return False
    if intent["require_all_accessibility_verified"] and not _all_accessibility_verified(accessibility):
        return False
    if intent["require_step_free"] and not _has_route_evidence(
        accessibility.get("slope_or_stairs"), STEP_FREE_EVIDENCE_TERMS
    ):
        return False
    if intent["require_flat_route"] and not _has_route_evidence(
        accessibility.get("slope_or_stairs"), FLAT_ROUTE_EVIDENCE_TERMS
    ):
        return False
    return True


def _document_tokens(place: Mapping[str, Any]) -> list[str]:
    weighted_parts: list[Any] = []
    weighted_parts.extend([place.get("name")] * 4)
    weighted_parts.extend([place.get("region")] * 2)
    weighted_parts.extend([place.get("category")] * 2)
    weighted_parts.extend([" ".join(CATEGORY_ALIASES.get(str(place.get("category") or ""), ()))] * 2)
    weighted_parts.extend([place.get("summary")] * 2)
    weighted_parts.extend(place.get("recommended_for") or [])
    weighted_parts.extend(place.get("avoid_for") or [])
    weighted_parts.extend(place.get("safety_notes") or [])
    weighted_parts.extend(place.get("operator_notes") or [])

    effort = place.get("effort")
    if isinstance(effort, Mapping):
        weighted_parts.extend(effort.values())

    accessibility = place.get("accessibility")
    if isinstance(accessibility, Mapping):
        for field, value in accessibility.items():
            if not isinstance(value, Mapping):
                continue
            state = str(value.get("state") or "unknown").casefold()
            weighted_parts.append(value.get("note"))
            repeats = 3 if state == "yes" else 2 if state == "partial" else 1 if state == "needs_check" else 0
            if repeats:
                aliases = " ".join(ACCESSIBILITY_ALIASES.get(str(field), (str(field),)))
                weighted_parts.extend([aliases] * repeats)

    for source in place.get("sources") or []:
        if isinstance(source, Mapping):
            weighted_parts.append(source.get("title"))

    tokens: list[str] = []
    for part in weighted_parts:
        tokens.extend(_tokenize(part))
    return tokens


def _bm25_scores(
    documents: list[list[str]], query: Counter[str]
) -> tuple[list[float], list[int]]:
    if not query:
        return [0.0] * len(documents), [0] * len(documents)

    document_frequencies = Counter()
    for document in documents:
        document_frequencies.update(set(document) & query.keys())
    average_length = sum(len(document) for document in documents) / max(1, len(documents))
    average_length = max(average_length, 1.0)
    corpus_size = len(documents)
    scores: list[float] = []
    matched_counts: list[int] = []

    for document in documents:
        frequencies = Counter(document)
        score = 0.0
        matched = 0
        for term, query_frequency in query.items():
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue
            matched += 1
            document_frequency = document_frequencies[term]
            inverse_document_frequency = math.log(
                1.0 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            normalization = term_frequency + BM25_K1 * (
                1.0 - BM25_B + BM25_B * len(document) / average_length
            )
            score += (
                inverse_document_frequency
                * (term_frequency * (BM25_K1 + 1.0) / normalization)
                * (1.0 + math.log(query_frequency))
            )
        scores.append(score)
        matched_counts.append(matched)
    return scores, matched_counts


def _substring_score(
    place: Mapping[str, Any], query_tokens: list[str], reasons: list[str]
) -> float:
    if not query_tokens:
        return 0.0
    meaningful = {token for token in query_tokens if len(token) >= 2}
    if not meaningful:
        return 0.0

    name = _normalized_text(place.get("name"))
    region = _normalized_text(place.get("region"))
    summary = _normalized_text(
        " ".join(
            [
                str(place.get("summary") or ""),
                *[str(item) for item in place.get("recommended_for") or []],
                *[str(item) for item in place.get("avoid_for") or []],
            ]
        )
    )
    accessibility_text = _normalized_text(
        " ".join(
            str(value.get("note") or "")
            for value in (place.get("accessibility") or {}).values()
            if isinstance(value, Mapping)
        )
    )

    name_matches = sum(token in name for token in meaningful)
    region_matches = sum(token in region for token in meaningful)
    summary_matches = sum(token in summary for token in meaningful)
    accessibility_matches = sum(token in accessibility_text for token in meaningful)
    score = min(12.0, name_matches * 4.0)
    score += min(4.0, region_matches * 1.5)
    score += min(4.0, summary_matches * 0.75)
    score += min(6.0, accessibility_matches * 1.0)
    if name_matches:
        reasons.append("검색어가 장소명과 일치")
    if region_matches:
        reasons.append("검색어가 지역 정보와 일치")
    if summary_matches:
        reasons.append("검색어가 장소 설명과 일치")
    if accessibility_matches:
        reasons.append("검색어가 접근성 근거와 일치")
    return score


def _structured_score(
    place: Mapping[str, Any], intent: Mapping[str, Any], reasons: list[str]
) -> float:
    score = 0.0
    if intent["regions"]:
        score += 5.0
        reasons.append("구조화된 지역 조건 충족")
    if intent["categories"]:
        score += 5.0
        reasons.append("구조화된 카테고리 조건 충족")
    if intent["accessibility"]:
        accessibility = place.get("accessibility") or {}
        for field in intent["accessibility"]:
            value = accessibility.get(field) if isinstance(accessibility, Mapping) else None
            state = str(value.get("state") if isinstance(value, Mapping) else "unknown").casefold()
            score += 4.0 if state == "yes" else 2.0
        reasons.append("필수 접근성 상태 충족")
    if intent["min_verification"]:
        score += 2.0
        reasons.append("최소 검증 상태 충족")
    return score


def _query_feature_score(
    place: Mapping[str, Any],
    *,
    query_accessibility: set[str],
    query_categories: set[str],
    reasons: list[str],
) -> float:
    score = 0.0
    accessibility = place.get("accessibility")
    accessibility = accessibility if isinstance(accessibility, Mapping) else {}
    for field in query_accessibility:
        value = accessibility.get(field)
        state = str(value.get("state") if isinstance(value, Mapping) else "unknown").casefold()
        score += {"yes": 3.5, "partial": 1.5, "needs_check": -1.0, "unknown": -1.5, "no": -4.0}.get(state, -1.5)
    if query_accessibility:
        reasons.append("질의의 접근성 요구와 상태를 대조")

    category = str(place.get("category") or "").casefold()
    if query_categories:
        if category in query_categories:
            score += 3.0
            reasons.append("질의의 장소 성격과 일치")
        else:
            score -= 0.5
    return score


def _trust_scores(
    place: Mapping[str, Any], *, as_of: date, reasons: list[str]
) -> tuple[float, float, str]:
    status = _verification_status(place)
    verification_score = VERIFICATION_SCORE.get(status, -2.0)
    if status == "verified":
        reasons.append("검증 상태가 확인됨")
    elif status == "partial":
        reasons.append("검증 상태가 일부 확인됨")
    else:
        reasons.append("검증 보강이 필요함")

    sources = [source for source in place.get("sources") or [] if isinstance(source, Mapping)]
    if any(_safe_url(source.get("url")) for source in sources):
        verification_score += 0.5
    else:
        verification_score -= 2.5
        reasons.append("출처 URL 보강이 필요함")

    checked_at = _checked_at(place)
    parsed = _parse_iso_date(checked_at)
    if parsed is None:
        return verification_score, -2.5, "unknown"
    age_days = (as_of - parsed).days
    if age_days < 0:
        return verification_score, -1.0, "future_date_check_required"
    if age_days <= 183:
        reasons.append("최근 6개월 이내 확인된 정보")
        return verification_score, 1.0, "recent"
    if age_days <= 365:
        reasons.append("반년 이상 경과해 최신성 재확인 권장")
        return verification_score, 0.0, "aging"
    reasons.append("확인 후 1년을 초과해 최신성 재검증 필요")
    return verification_score, -3.0, "stale"


def _evidence_bundle(place: Mapping[str, Any], *, freshness: str) -> dict[str, Any]:
    status = _verification_status(place)
    checked_at = _checked_at(place)
    source_evidence: list[dict[str, Any]] = []
    place_id = str(place.get("id") or "")
    for source_index, source in enumerate(place.get("sources") or [], start=1):
        if not isinstance(source, Mapping):
            continue
        source_url = _safe_url(source.get("url"))
        source_evidence.append(
            {
                "evidence_id": _evidence_id(place_id, source_index, source_url),
                "title": str(source.get("title") or "")[:240],
                "url": source_url,
                "type": str(source.get("type") or "unknown")[:80],
                "checked_at": checked_at,
                "status": status,
            }
        )

    accessibility_evidence: dict[str, dict[str, Any]] = {}
    accessibility = place.get("accessibility")
    if isinstance(accessibility, Mapping):
        for field in sorted(ACCESSIBILITY_ALIASES):
            value = accessibility.get(field)
            if not isinstance(value, Mapping):
                continue
            source_ref = str(value.get("source_ref") or "").strip()
            matched_source = _source_for_ref(source_evidence, source_ref)
            accessibility_evidence[field] = {
                "evidence_id": _field_evidence_id(place_id, field),
                "state": str(value.get("state") or "unknown"),
                "note": _bounded_evidence_text(value.get("note"), EVIDENCE_NOTE_MAX_LENGTH),
                "source_ref": source_ref or None,
                "source_title": matched_source.get("title") if matched_source else None,
                "source_url": matched_source.get("url") if matched_source else None,
            }

    return {
        "place_id": place_id,
        "verification": {
            "status": status,
            "checked_at": checked_at,
            "freshness": freshness,
        },
        "sources": source_evidence,
        "accessibility": accessibility_evidence,
    }


def _evidence_id(place_id: str, source_index: int, source_url: str) -> str:
    payload = f"{place_id}\n{source_index}\n{source_url}".encode("utf-8")
    return "ev_" + hashlib.sha256(payload).hexdigest()[:16]


def _field_evidence_id(place_id: str, field: str) -> str:
    payload = f"accessibility_field\n{place_id}\n{field}".encode("utf-8")
    return "ev_" + hashlib.sha256(payload).hexdigest()[:16]


def _source_for_ref(
    sources: list[dict[str, Any]], source_ref: str
) -> dict[str, Any] | None:
    """Best-effort link from a bounded corpus reference to its public source."""

    if not source_ref:
        return None
    normalized_ref = _normalized_text(source_ref)
    hints = {
        "easyjeju": ("easyjejunet", "이지제주"),
        "jeju_roadview_facility_status": ("15109153", "로드뷰"),
        "open_tourism": ("accessvisitkorea", "열린관광"),
        "airport": ("airportcokr", "제주국제공항"),
        "tourism_weak_recommendation_courses": ("15117357", "관광약자유형별"),
    }.get(source_ref.casefold(), ())
    normalized_hints = tuple(_normalized_text(hint) for hint in hints)

    for source in sources:
        haystack = _normalized_text(
            f"{source.get('title') or ''} {source.get('url') or ''} {source.get('type') or ''}"
        )
        if normalized_ref and normalized_ref in haystack:
            return source
        if normalized_hints and any(hint in haystack for hint in normalized_hints):
            return source

    # Small fixtures and cards with one source can safely resolve an opaque ref.
    return sources[0] if len(sources) == 1 else None


def _bounded_evidence_text(value: Any, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _query_accessibility_fields(query: str) -> set[str]:
    normalized = _normalized_text(query)
    return {
        field
        for field, aliases in ACCESSIBILITY_ALIASES.items()
        if any(_normalized_text(alias) in normalized for alias in aliases)
    }


def _query_categories(query: str) -> set[str]:
    normalized = _normalized_text(query)
    return {
        category
        for category, aliases in CATEGORY_ALIASES.items()
        if any(_normalized_text(alias) in normalized for alias in aliases)
    }


def _tokenize(value: Any) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_PATTERN.findall(str(value or "").casefold()):
        tokens.append(token)
        stripped = _strip_korean_suffix(token)
        if stripped != token:
            tokens.append(stripped)
    return tokens


def _strip_korean_suffix(token: str) -> str:
    for suffix in KOREAN_SUFFIXES:
        if token.endswith(suffix) and len(token) >= len(suffix) + 2:
            return token[: -len(suffix)]
    return token


def _canonical_category(value: Any) -> str:
    normalized = _normalized_text(value)
    for category, aliases in CATEGORY_ALIASES.items():
        if normalized == _normalized_text(category) or normalized in {
            _normalized_text(alias) for alias in aliases
        }:
            return category
    return ""


def _canonical_accessibility_field(value: Any) -> str:
    normalized = _normalized_text(value)
    for field, aliases in ACCESSIBILITY_ALIASES.items():
        if normalized == _normalized_text(field) or normalized in {
            _normalized_text(alias) for alias in aliases
        }:
            return field
    return ""


def _canonical_accessibility_state(value: Any) -> str:
    normalized = _normalized_text(value)
    aliases = {
        "yes": {"yes", "true", "confirmed", "확인", "가능"},
        "partial": {"partial", "일부확인", "부분가능"},
        "needs_check": {"needscheck", "확인필요", "재확인"},
        "unknown": {"unknown", "알수없음", "미확인"},
        "no": {"no", "false", "불가", "없음"},
    }
    for state, values in aliases.items():
        if normalized in {_normalized_text(item) for item in values}:
            return state
    return normalized if normalized in ACCESSIBILITY_STATES else ""


def _canonical_verification(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in VERIFICATION_RANK else ""


def _canonical_effort_level(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    return normalized if normalized in EFFORT_RANK else ""


def _effort_at_most(value: Any, maximum: str) -> bool:
    actual = _canonical_effort_level(value)
    return bool(actual and EFFORT_RANK[actual] <= EFFORT_RANK[maximum])


def _all_accessibility_verified(accessibility: Mapping[str, Any]) -> bool:
    for field in ACCESSIBILITY_ALIASES:
        value = accessibility.get(field)
        if not isinstance(value, Mapping):
            return False
        if str(value.get("state") or "unknown").casefold() not in SAFE_REQUIRED_ACCESSIBILITY_STATES:
            return False
        if not str(value.get("source_ref") or "").strip():
            return False
    return True


def _has_route_evidence(value: Any, evidence_terms: tuple[str, ...]) -> bool:
    if not isinstance(value, Mapping):
        return False
    if str(value.get("state") or "unknown").casefold() not in SAFE_REQUIRED_ACCESSIBILITY_STATES:
        return False
    note = re.sub(r"\s+", " ", str(value.get("note") or "")).strip()
    return any(term in note for term in evidence_terms)


def _has_operating_hours_evidence(
    visit_info: Mapping[str, Any], *, require_24_hours: bool = False, require_night: bool = False
) -> bool:
    if visit_info.get("open_24_hours") is True:
        return True
    hours = " ".join(
        str(visit_info.get(key) or "")
        for key in ("operating_hours", "opening_hours", "hours")
    )
    compact = re.sub(r"\s+", "", hours).casefold()
    if not compact:
        return False
    if any(marker in compact for marker in ("24시간", "24hours", "00:00-24:00", "00:00~24:00")):
        return True
    if require_24_hours:
        return False
    if require_night and any(marker in compact for marker in ("야간", "심야", "night")):
        return True
    if require_night:
        closing_hours = [int(value) for value in re.findall(r"(?:-|~)([01]?\d|2[0-3]):\d{2}", compact)]
        return any(hour >= 20 for hour in closing_hours)
    return True


def _verification_status(place: Mapping[str, Any]) -> str:
    verification = place.get("verification")
    if not isinstance(verification, Mapping):
        return "needs_check"
    return _canonical_verification(verification.get("status")) or "needs_check"


def _checked_at(place: Mapping[str, Any]) -> str | None:
    verification = place.get("verification")
    if not isinstance(verification, Mapping):
        return None
    value = str(verification.get("checked_at") or "").strip()
    return value if _parse_iso_date(value) else None


def _parse_iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _region_matches(place_region: Any, required_region: str) -> bool:
    actual = _normalized_text(place_region)
    required = _normalized_text(required_region)
    if required in {"제주", "제주도", "제주특별자치도"}:
        return bool(actual)
    return bool(required and actual and (required in actual or actual in required))


def _safe_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    return url[:2048]


def _filter_trace(intent: Mapping[str, Any]) -> list[str]:
    filters = ["active_status", "open_service", "available_verification"]
    if intent["regions"]:
        filters.append("region")
    if intent["categories"]:
        filters.append("category")
    if intent["excluded_categories"]:
        filters.append("excluded_category")
    if intent["accessibility"]:
        filters.append("required_accessibility")
    if intent["min_verification"]:
        filters.append("minimum_verification")
    if intent["require_all_accessibility_verified"]:
        filters.append("all_accessibility_verified")
    if intent["require_24_hours"]:
        filters.append("operating_24_hours")
    if intent["require_night_hours"]:
        filters.append("night_operating_hours")
    if intent["max_weather_sensitivity"]:
        filters.append("weather_sensitivity")
    if intent["max_outdoor_exposure"]:
        filters.append("outdoor_exposure")
    if intent["max_walking_level"]:
        filters.append("walking_level")
    if intent["require_step_free"]:
        filters.append("step_free_evidence")
    if intent["require_flat_route"]:
        filters.append("flat_route_evidence")
    if intent["excluded_warning_terms"]:
        filters.append("avoid_warning_collision")
    return filters


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item) for item in value if isinstance(item, (str, int, float)) and not isinstance(item, bool)]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    return []


def _has_intent_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, frozenset, str)):
        return bool(value)
    return value is not None


def _normalized_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").casefold())


def _stable_place_digest(place: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            dict(place), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        encoded = repr(sorted((str(key), str(value)) for key, value in place.items())).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
