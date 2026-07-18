"""Runtime recommendation service with optional GPT explanation support."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from typing import Any, Protocol

from src.app_recommendations import SAFETY_NOTICE, app_place_result
from src.rag_query import parse_query_intent
from src.rag_reranking import (
    STRUCTURED_RERANKER_VERSION,
    rerank_place_scores_by_intent,
)
from src.rag_retrieval import ACCESSIBILITY_ALIASES, retrieve_place_candidates
from src.recommendation_evidence import is_grounded_recommendation_candidate
from src.route_optimization import optimize_course_route
from src.scoring import PlaceScore, build_recommendation_result, rank_places


TRAVELER_SUMMARY_KEYS = (
    "traveler_type",
    "mobility_conditions",
    "preferred_themes",
    "required_accessibility",
    "avoid",
)


DEFAULT_OPENAI_MODEL = "gpt-5-mini"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_AI_SUMMARY_MAX_OUTPUT_TOKENS = 2200
OPENAI_AI_SUMMARY_TIMEOUT_SECONDS = 35
OPENAI_AI_SUMMARY_MAX_ATTEMPTS = 2
OPENAI_AI_SUMMARY_RETRYABLE_HTTP_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})
AI_HEADLINE_MAX_LENGTH = 80
AI_LIST_ITEM_MAX_LENGTH = 100
CLOSED_SERVICE_STATUSES = frozenset({"permanently_closed", "temporarily_closed"})
RAG_RETRIEVAL_LIMIT = 24
RAG_RESERVE_LIMIT = 50
RAG_CANDIDATE_POOL_LIMIT = 50
RAG_PRIMARY_PROTECTION_MARGIN = 8
RAG_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
RAG_RETRIEVER_NAME = "deterministic_bm25_structured_v1"
_REQUIRED_ACCESSIBILITY_LOOKUP = {
    re.sub(r"[^0-9a-z가-힣]+", "", label.casefold()): field
    for field, aliases in ACCESSIBILITY_ALIASES.items()
    for label in (field, *aliases)
}
_REQUIRED_ACCESSIBILITY_HARD_FILTER_FIELDS = frozenset(
    ACCESSIBILITY_ALIASES
)
_ACCESSIBILITY_FACT_PRIORITY = {
    "wheelchair_access": 0,
    "accessible_toilet": 1,
    "parking": 2,
    "rest_area": 3,
    "slope_or_stairs": 4,
    "surface_condition": 5,
}


AI_SUMMARY_TEXT_FORMAT = {
    "type": "json_schema",
    "name": "jeju_accessible_travel_summary",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["headline", "rationale", "cautions", "next_checks", "evidence_ids"],
        "properties": {
            "headline": {"type": "string"},
            "rationale": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "evidence_ids"],
                    "properties": {
                        "text": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 8,
                        },
                    },
                },
                "maxItems": 4,
            },
            "cautions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "evidence_ids"],
                    "properties": {
                        "text": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 8,
                        },
                    },
                },
                "maxItems": 4,
            },
            "next_checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "evidence_ids"],
                    "properties": {
                        "text": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 8,
                        },
                    },
                },
                "maxItems": 4,
            },
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
        },
    },
}


class RecommendationExplanationClient(Protocol):
    def generate_summary(self, context: dict[str, Any], *, model: str) -> dict[str, Any]:
        """Return a Korean summary object for an already-scored recommendation."""


def normalize_traveler_summary(value: dict[str, Any] | None) -> dict[str, list[str]]:
    summary = value or {}
    normalized: dict[str, list[str]] = {}
    for key in TRAVELER_SUMMARY_KEYS:
        raw = summary.get(key, [])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raw = []
        normalized[key] = _unique_strings(raw)
    return normalized


def build_runtime_recommendation(
    places: list[dict[str, Any]],
    traveler_summary: dict[str, Any],
    *,
    today: date,
    query: str = "",
    limit: int = 4,
    use_ai: bool = True,
    ai_model: str = DEFAULT_OPENAI_MODEL,
    explanation_client: RecommendationExplanationClient | None = None,
    location_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base_summary = normalize_traveler_summary(traveler_summary)
    query_intent = parse_query_intent(query, base_summary)
    query_text = query_intent["query_text"]
    normalized_summary = (
        normalize_traveler_summary(query_intent["traveler_summary"])
        if query_text
        else base_summary
    )
    safe_limit = max(1, min(int(limit or 4), 4))
    open_candidates = [
        place
        for place in places
        if is_grounded_recommendation_candidate(place)
        and _is_open_service_candidate(place)
    ]
    candidate_places = open_candidates
    retrieval_hits: list[dict[str, Any]] = []
    primary_spot_ids: set[str] = set()
    retrieval_status = "not_requested"
    data_gaps: list[str] = []

    if query_text:
        resource_types = query_intent.get("resource_types", [])
        if resource_types:
            retrieval_status = "resource_data_gap"
            data_gaps = list(resource_types)
            candidate_places = []
        else:
            retrieval_constraints = _retrieval_constraints(query_intent)
            if _should_abstain_without_constraints(query_intent, retrieval_constraints):
                retrieval_hits = []
                candidate_places = []
                retrieval_status = "no_match"
            else:
                retrieval_hits, primary_spot_ids = _retrieve_candidate_hits(
                    open_candidates,
                    query_text=query_text,
                    retrieval_constraints=retrieval_constraints,
                    safe_limit=safe_limit,
                    today=today,
                )
                candidate_places = [hit["place"] for hit in retrieval_hits]
                retrieval_status = "applied" if candidate_places else "no_match"

    place_index = {place.get("id", ""): place for place in candidate_places}
    local_scores = rank_places(candidate_places, normalized_summary, limit=None, today=today)
    scores = (
        rerank_place_scores_by_intent(
            retrieval_hits,
            local_scores,
            query_text=query_text,
            limit=safe_limit,
        )
        if query_text
        else local_scores[:safe_limit]
    )
    recommendation = build_recommendation_result(
        scores,
        normalized_summary,
        safety_notice=SAFETY_NOTICE,
        title="맞춤 접근성 추천 코스",
    )
    if retrieval_status in {"resource_data_gap", "no_match"}:
        recommendation["course"]["route"] = []
    else:
        recommendation["course"]["route"] = optimize_course_route(
            recommendation["course"]["route"],
            location_index or {},
        )
    result_places = [
        app_place_result(score, place_index.get(score.spot_id, {}), location_index=location_index or {})
        for score in scores
    ]
    retrieval = _build_retrieval_response(
        status=retrieval_status,
        query_intent=query_intent if query_text else None,
        hits=retrieval_hits,
        selected_spot_ids=[score.spot_id for score in scores],
        corpus_count=len(open_candidates),
        data_gaps=data_gaps,
    )
    ai_summary = build_ai_summary(
        recommendation,
        result_places,
        normalized_summary,
        use_ai=use_ai,
        ai_model=ai_model,
        explanation_client=explanation_client,
        retrieval=retrieval,
    )
    return {
        "generated_at": today.isoformat(),
        "engine": {
            "scoring": "local_accessibility_score_v1",
            "retrieval": retrieval["engine"],
            "reranking": STRUCTURED_RERANKER_VERSION if query_text else None,
            "ai_model": ai_model,
            "ai_status": ai_summary["status"],
        },
        "traveler_summary": normalized_summary,
        "recommendation": recommendation,
        "places": result_places,
        "retrieval": retrieval,
        "ai_summary": ai_summary,
        "safety_notice": SAFETY_NOTICE,
    }


def _is_open_service_candidate(place: dict[str, Any]) -> bool:
    visit_info = place.get("visit_info")
    if not isinstance(visit_info, dict):
        return True
    return visit_info.get("service_status") not in CLOSED_SERVICE_STATUSES


def _retrieve_candidate_hits(
    places: list[dict[str, Any]],
    *,
    query_text: str,
    retrieval_constraints: dict[str, Any],
    safe_limit: int,
    today: date,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Fuse lexical precision hits with a constraint-safe reserve.

    The reserve runs only after at least one content-relevant primary hit, so an
    unmatched query cannot turn into a generic fallback recommendation. Both
    channels use the same hard constraints, and the bounded merge keeps the
    runtime predictable for the reviewed local corpus.
    """

    primary_hits = retrieve_place_candidates(
        places,
        query=query_text,
        intent=retrieval_constraints,
        limit=max(RAG_RETRIEVAL_LIMIT, safe_limit * 4),
        as_of=today,
    )
    if not primary_hits:
        return [], set()

    reserve_hits = retrieve_place_candidates(
        places,
        query="",
        intent=retrieval_constraints,
        limit=RAG_RESERVE_LIMIT,
        as_of=today,
    )
    merged_hits = _merge_candidate_hits(primary_hits, reserve_hits)
    primary_spot_ids = {
        str(hit.get("place", {}).get("id") or "")
        for hit in primary_hits
        if isinstance(hit.get("place"), dict)
        and str(hit.get("place", {}).get("id") or "")
    }
    return merged_hits, primary_spot_ids


def _merge_candidate_hits(
    primary_hits: list[dict[str, Any]],
    reserve_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, hits in (
        ("content_primary", primary_hits),
        ("constraint_safe_reserve", reserve_hits),
    ):
        for hit in hits:
            place = hit.get("place") if isinstance(hit, dict) else None
            spot_id = str(place.get("id") or "") if isinstance(place, dict) else ""
            if not spot_id or spot_id in seen:
                continue
            tagged_hit = dict(hit)
            tagged_hit["trace"] = {
                **(dict(hit.get("trace") or {})),
                "candidate_source": source,
            }
            merged.append(tagged_hit)
            seen.add(spot_id)
            if len(merged) >= RAG_CANDIDATE_POOL_LIMIT:
                return merged
    return merged


def _apply_primary_protection(
    scores: list[PlaceScore],
    *,
    primary_spot_ids: set[str],
    limit: int,
) -> list[PlaceScore]:
    """Let a reserve candidate enter only with a material local-score gain."""

    indexed_scores = list(enumerate(scores))
    indexed_scores.sort(
        key=lambda item: (
            item[1].total
            + (
                RAG_PRIMARY_PROTECTION_MARGIN
                if item[1].spot_id in primary_spot_ids
                else 0
            ),
            RAG_CONFIDENCE_RANK.get(getattr(item[1], "confidence", "low"), -1),
            -item[0],
        ),
        reverse=True,
    )
    return [score for _, score in indexed_scores[:limit]]


def _retrieval_constraints(query_intent: dict[str, Any]) -> dict[str, Any]:
    """Use only high-confidence fields as retrieval hard filters.

    The retrieval layer canonicalizes supported accessibility labels and ignores
    unknown ones, so adding a future profile label cannot accidentally remove
    every candidate.
    """

    required_accessibility = _unique_strings(query_intent.get("required_accessibility", []))
    traveler_summary = query_intent.get("traveler_summary")
    if isinstance(traveler_summary, dict):
        required_accessibility = _unique_strings(
            required_accessibility + _unique_strings(
                traveler_summary.get("required_accessibility", [])
            )
        )
    required_accessibility = _supported_required_accessibility(required_accessibility)

    signals = query_intent.get("signals")
    signals = signals if isinstance(signals, dict) else {}
    constraints = {
        "regions": query_intent.get("regions", []),
        "categories": query_intent.get("categories", []),
        "exclude_categories": query_intent.get("excluded_categories", []),
        "required_accessibility": required_accessibility,
        "exclude_warning_terms": (
            list(traveler_summary.get("avoid") or [])
            if isinstance(traveler_summary, dict)
            else []
        ),
    }
    if signals.get("strict_verification") is True:
        constraints["verified_only"] = True
        constraints["require_all_accessibility_verified"] = True
    if signals.get("require_24_hours") is True:
        constraints["require_24_hours"] = True
    if signals.get("require_night_hours") is True:
        constraints["require_night_hours"] = True
    if signals.get("weather_protected") is True:
        constraints["max_weather_sensitivity"] = "medium"
        constraints["max_outdoor_exposure"] = "medium"
    if signals.get("low_walking_burden") is True:
        constraints["max_walking_level"] = "low"
        constraints["max_outdoor_exposure"] = "medium"
        if isinstance(traveler_summary, dict):
            traveler_types = set(traveler_summary.get("traveler_type") or [])
            preferred_themes = set(traveler_summary.get("preferred_themes") or [])
            if "recovery_traveler" in traveler_types and "휴식" in preferred_themes:
                constraints["max_outdoor_exposure"] = "low"
    if signals.get("require_step_free") is True:
        constraints["require_step_free"] = True
    if signals.get("require_flat_route") is True:
        constraints["require_flat_route"] = True
    return constraints


def _should_abstain_without_constraints(
    query_intent: dict[str, Any], constraints: dict[str, Any]
) -> bool:
    signals = query_intent.get("signals")
    if not isinstance(signals, dict) or signals.get("no_fallback") is not True:
        return False
    meaningful_keys = {
        "regions",
        "categories",
        "exclude_categories",
        "required_accessibility",
        "verified_only",
        "require_24_hours",
        "require_night_hours",
        "max_weather_sensitivity",
        "max_outdoor_exposure",
        "max_walking_level",
        "require_step_free",
        "require_flat_route",
        "exclude_warning_terms",
    }
    if any(constraints.get(key) for key in meaningful_keys):
        return False
    query_text = str(query_intent.get("query_text") or "")
    return "제 조건" in query_text and "빈 결과" in query_text


def _supported_required_accessibility(values: list[str]) -> list[str]:
    fields = []
    for value in values:
        normalized = re.sub(r"[^0-9a-z가-힣]+", "", value.casefold())
        field = _REQUIRED_ACCESSIBILITY_LOOKUP.get(normalized)
        if field in _REQUIRED_ACCESSIBILITY_HARD_FILTER_FIELDS:
            fields.append(field)
    return _unique_strings(fields)


def _build_retrieval_response(
    *,
    status: str,
    query_intent: dict[str, Any] | None,
    hits: list[dict[str, Any]],
    selected_spot_ids: list[str],
    corpus_count: int,
    data_gaps: list[str],
) -> dict[str, Any]:
    hit_index = {
        str(hit.get("place", {}).get("id") or ""): hit
        for hit in hits
        if isinstance(hit, dict) and isinstance(hit.get("place"), dict)
    }
    matches: list[dict[str, Any]] = []
    for spot_id in selected_spot_ids:
        hit = hit_index.get(spot_id)
        if not hit:
            continue
        evidence = hit.get("evidence_bundle") if isinstance(hit.get("evidence_bundle"), dict) else {}
        matches.append(
            {
                "spot_id": spot_id,
                "retrieval_score": hit.get("retrieval_score", 0),
                "retrieval_reasons": list(hit.get("retrieval_reasons") or [])[:8],
                "evidence_bundle": evidence,
                "trace": dict(hit.get("trace") or {}),
            }
        )

    public_intent = None
    if query_intent is not None:
        public_intent = {
            "intent": query_intent.get("intent", "unknown"),
            "regions": list(query_intent.get("regions") or []),
            "categories": list(query_intent.get("categories") or []),
            "resource_types": list(query_intent.get("resource_types") or []),
            "signals": dict(query_intent.get("signals") or {}),
        }

    return {
        "status": status,
        "engine": RAG_RETRIEVER_NAME if query_intent is not None else "not_requested",
        "corpus_count": corpus_count,
        "retrieved_count": len(hits),
        "query_intent": public_intent,
        "data_gaps": list(data_gaps),
        "matches": matches,
    }


def build_ai_summary(
    recommendation: dict[str, Any],
    places: list[dict[str, Any]],
    traveler_summary: dict[str, list[str]],
    *,
    use_ai: bool,
    ai_model: str,
    explanation_client: RecommendationExplanationClient | None,
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not use_ai:
        return empty_ai_summary("skipped", ai_model, "자동 설명을 요청하지 않아 기본 추천 기준만 사용했습니다.")

    retrieval_status = str((retrieval or {}).get("status") or "not_requested")
    grounded_query = _is_grounded_retrieval_request(retrieval)
    evidence_index = _retrieval_evidence_index(retrieval)
    if grounded_query and retrieval_status != "applied":
        return empty_ai_summary(
            "blocked_retrieval",
            ai_model,
            "조건에 맞는 확인 자료가 없어 자동 설명을 만들지 않았습니다.",
        )
    if grounded_query and not evidence_index:
        return empty_ai_summary(
            "insufficient_evidence",
            ai_model,
            "확인할 수 있는 공식 자료가 없어 자동 설명을 만들지 않았습니다.",
        )
    if explanation_client is None:
        return empty_ai_summary("disabled_no_key", ai_model, "지금은 자동 설명을 사용할 수 없어 기본 추천 기준만 표시합니다.")

    context = ai_prompt_context(recommendation, places, traveler_summary, retrieval=retrieval)
    try:
        generated = explanation_client.generate_summary(context, model=ai_model)
    except Exception:
        return empty_ai_summary("error", ai_model, "자동 설명을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.")

    summary = normalize_ai_summary(
        generated,
        ai_model,
        evidence_index=evidence_index,
    )
    if grounded_query and not summary["citations"]:
        return empty_ai_summary(
            "ungrounded",
            ai_model,
            "설명을 확인할 수 있는 출처가 충분하지 않아 결과를 표시하지 않았습니다.",
        )
    return summary


def _is_grounded_retrieval_request(retrieval: dict[str, Any] | None) -> bool:
    if not isinstance(retrieval, dict):
        return False
    status = str(retrieval.get("status") or "not_requested")
    return status != "not_requested"


def empty_ai_summary(status: str, model: str, note: str) -> dict[str, Any]:
    return {
        "status": status,
        "model": model,
        "headline": "",
        "rationale": [],
        "cautions": [],
        "next_checks": [],
        "claim_citations": [],
        "citations": [],
        "note": note,
    }


def normalize_ai_summary(
    value: dict[str, Any],
    model: str,
    *,
    evidence_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_index = evidence_index or {}
    normalized_sections: dict[str, list[str]] = {}
    claim_citations: list[dict[str, Any]] = []
    for section in ("rationale", "cautions", "next_checks"):
        texts, section_claims = _normalize_ai_claims(
            value.get(section, []),
            section=section,
            evidence_index=evidence_index,
        )
        normalized_sections[section] = texts
        claim_citations.extend(section_claims)

    top_level_citations = _resolve_ai_citations(value.get("evidence_ids"), evidence_index)
    citations = _merge_ai_citations(
        top_level_citations,
        *(claim["citations"] for claim in claim_citations),
    )
    return {
        "status": "success",
        "model": model,
        "headline": clean_ai_text(value.get("headline") or "조건에 맞춘 접근성 추천입니다.", AI_HEADLINE_MAX_LENGTH),
        "rationale": normalized_sections["rationale"],
        "cautions": normalized_sections["cautions"],
        "next_checks": normalized_sections["next_checks"],
        "claim_citations": claim_citations,
        "citations": citations,
        "note": clean_ai_text(value.get("note") or "", AI_LIST_ITEM_MAX_LENGTH),
    }


def _normalize_ai_claims(
    values: Any,
    *,
    section: str,
    evidence_index: dict[str, dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Normalize structured model claims while accepting legacy string arrays."""

    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return [], []

    texts: list[str] = []
    claims: list[dict[str, Any]] = []
    claim_index_by_text: dict[str, int] = {}
    for value in values:
        raw_evidence_ids: Any = []
        if isinstance(value, dict):
            text = clean_ai_text(value.get("text"), AI_LIST_ITEM_MAX_LENGTH)
            raw_evidence_ids = value.get("evidence_ids")
        else:
            text = clean_ai_text(value, AI_LIST_ITEM_MAX_LENGTH)
        if not text:
            continue

        resolved = _resolve_ai_citations(raw_evidence_ids, evidence_index)
        evidence_ids = [str(citation["evidence_id"]) for citation in resolved]
        existing_index = claim_index_by_text.get(text)
        if existing_index is not None:
            existing = claims[existing_index]
            existing["citations"] = _merge_ai_citations(existing["citations"], resolved)
            existing["evidence_ids"] = [
                str(citation["evidence_id"]) for citation in existing["citations"]
            ]
            continue
        if len(texts) >= 4:
            break

        index = len(texts)
        texts.append(text)
        claim_index_by_text[text] = index
        claims.append(
            {
                "section": section,
                "index": index,
                "text": text,
                "evidence_ids": evidence_ids,
                "citations": resolved,
            }
        )
    return texts, claims


def clean_ai_text_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    cleaned = [clean_ai_text(value, AI_LIST_ITEM_MAX_LENGTH) for value in values]
    return _unique_strings([value for value in cleaned if value])


def clean_ai_text(value: Any, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    text = re.sub(r"(.)\1{8,}", r"\1\1\1", text)
    if len(text) <= max_length:
        return text

    cutoff = -1
    for separator in ("다.", "요.", ".", "!", "?"):
        cutoff = max(cutoff, text.rfind(separator, 0, max_length))
    if cutoff >= max_length // 2:
        return text[: cutoff + 1].strip()
    return text[:max_length].rstrip() + "..."


def ai_prompt_context(
    recommendation: dict[str, Any],
    places: list[dict[str, Any]],
    traveler_summary: dict[str, list[str]],
    *,
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "traveler_summary": traveler_summary,
        "course": recommendation.get("course", {}),
        "score": recommendation.get("score", {}),
        "fit_reasons": recommendation.get("fit_reasons", [])[:8],
        "deduction_reasons": recommendation.get("deduction_reasons", [])[:8],
        "check_before_visit": recommendation.get("check_before_visit", [])[:8],
        "retrieval": {
            "status": (retrieval or {}).get("status", "not_requested"),
            "evidence": _ai_prompt_evidence(retrieval),
        },
        "places": [
            {
                "name": place.get("name"),
                "region": place.get("region"),
                "category": place.get("category"),
                "score": place.get("score"),
                "fit_reasons": place.get("fit_reasons", [])[:3],
                "deduction_reasons": place.get("deduction_reasons", [])[:3],
                "safety_notes": place.get("safety_notes", [])[:3],
                "avoid_for": place.get("avoid_for", [])[:3],
            }
            for place in places[:4]
        ],
    }


def _ai_prompt_evidence(retrieval: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Keep grounding facts while omitting citation-only prompt payload."""

    rows: list[dict[str, Any]] = []
    for evidence in list(_retrieval_evidence_index(retrieval).values())[:16]:
        row = {
            key: evidence.get(key)
            for key in (
                "evidence_id",
                "evidence_kind",
                "spot_id",
                "field",
                "state",
                "note",
                "source_title",
                "checked_at",
                "verification_status",
            )
            if evidence.get(key) not in (None, "")
        }
        if row:
            rows.append(row)
    return rows


def _retrieval_evidence_index(
    retrieval: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(retrieval, dict):
        return index
    accessibility_groups: list[list[dict[str, Any]]] = []
    source_rows: list[dict[str, Any]] = []
    for match in retrieval.get("matches") or []:
        if not isinstance(match, dict):
            continue
        spot_id = str(match.get("spot_id") or "")
        evidence = match.get("evidence_bundle")
        if not isinstance(evidence, dict):
            continue
        verification = evidence.get("verification") if isinstance(evidence.get("verification"), dict) else {}
        accessibility_rows: list[dict[str, Any]] = []
        accessibility = evidence.get("accessibility")
        if isinstance(accessibility, dict):
            for field, fact in sorted(
                accessibility.items(),
                key=lambda item: (_ACCESSIBILITY_FACT_PRIORITY.get(item[0], 99), item[0]),
            ):
                if not isinstance(fact, dict):
                    continue
                evidence_id = str(fact.get("evidence_id") or "")
                source_url = str(fact.get("source_url") or "")
                if not evidence_id or not source_url.startswith(("https://", "http://")):
                    continue
                note = str(fact.get("note") or "")[:320]
                state = str(fact.get("state") or "unknown")[:40]
                accessibility_rows.append(
                    {
                        "evidence_id": evidence_id,
                        "evidence_kind": "accessibility_fact",
                        "spot_id": spot_id,
                        "field": str(field)[:80],
                        "state": state,
                        "note": note,
                        "claim": note or f"{field} 상태: {state}",
                        "source_title": str(fact.get("source_title") or "")[:240],
                        "source_url": source_url[:2048],
                        "checked_at": verification.get("checked_at"),
                        "verification_status": verification.get("status") or "needs_check",
                    }
                )
        if accessibility_rows:
            accessibility_groups.append(accessibility_rows)

        for source in evidence.get("sources") or []:
            if not isinstance(source, dict):
                continue
            evidence_id = str(source.get("evidence_id") or "")
            source_url = str(source.get("url") or "")
            if not evidence_id or not source_url.startswith(("https://", "http://")):
                continue
            source_rows.append({
                "evidence_id": evidence_id,
                "evidence_kind": "source",
                "spot_id": spot_id,
                "source_title": str(source.get("title") or "")[:240],
                "source_url": source_url[:2048],
                "checked_at": source.get("checked_at") or verification.get("checked_at"),
                "verification_status": source.get("status") or verification.get("status") or "needs_check",
            })

    # Round-robin facts so the bounded prompt represents every selected place.
    for fact_index in range(max((len(group) for group in accessibility_groups), default=0)):
        for group in accessibility_groups:
            if fact_index < len(group):
                row = group[fact_index]
                index[row["evidence_id"]] = row
    for row in source_rows:
        index.setdefault(row["evidence_id"], row)
    return index


def _resolve_ai_citations(
    values: Any,
    evidence_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        evidence_id = str(value or "").strip()
        if evidence_id in seen or evidence_id not in evidence_index:
            continue
        citations.append(dict(evidence_index[evidence_id]))
        seen.add(evidence_id)
        if len(citations) >= 8:
            break
    return citations


def _merge_ai_citations(*citation_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in citation_groups:
        for citation in group:
            evidence_id = str(citation.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in seen:
                continue
            citations.append(dict(citation))
            seen.add(evidence_id)
    return citations


class OpenAIExplanationResponseError(RuntimeError):
    """Safe, user-displayable failure for an unusable Responses API result."""


class OpenAIResponsesExplanationClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: int = OPENAI_AI_SUMMARY_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def generate_summary(self, context: dict[str, Any], *, model: str) -> dict[str, Any]:
        reasoning_effort = "none" if model.startswith("gpt-5.6") else "minimal"
        request_body = {
            "model": model,
            "reasoning": {"effort": reasoning_effort},
            "store": False,
            "text": {"format": AI_SUMMARY_TEXT_FORMAT, "verbosity": "low"},
            "max_output_tokens": OPENAI_AI_SUMMARY_MAX_OUTPUT_TOKENS,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "너는 제주 접근성 여행 추천 서비스의 설명 생성기다. "
                        "의료 판단이나 방문 가능 보장을 하지 말고, 제공된 점수와 근거만 사용한다. "
                        "장소가 안전하다고 단정하지 말고, 점수·시설·검수 상태를 근거로 설명한다. "
                        "접근성 시설 주장은 evidence_kind가 accessibility_fact인 항목의 field, state, note만 사용한다. "
                        "검색 근거를 언급할 때는 retrieval.evidence에 있는 evidence_id만 사용한다. "
                        "모든 문장은 한국어로 작성한다."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "다음 추천 결과를 접근성 여행자가 바로 이해할 수 있게 요약하라. "
                        "headline은 35자 안팎의 차분한 한 문장으로 쓴다. "
                        "rationale은 핵심 근거만 최대 3개, cautions와 next_checks는 각각 최대 2개로 쓴다. "
                        "각 항목은 중복 없이 70자 이내의 한 문장으로 쓴다. "
                        "cautions에는 현장 변수, 운영 여부, 혼잡, 음식 제한, 날씨 민감 요소처럼 확정할 수 없는 부분을 쓰고, "
                        "next_checks에는 방문 전 실제로 확인할 항목만 쓴다. "
                        "새로운 장소명, 없는 시설, 의학적 조언은 만들지 않는다. "
                        "rationale, cautions, next_checks의 각 항목은 text와 evidence_ids를 갖는 객체로 작성한다. "
                        "각 문장의 evidence_ids에는 그 문장을 직접 뒷받침하는 retrieval.evidence의 ID만 넣고, "
                        "근거가 없는 문장은 빈 배열로 둔다. 최상위 evidence_ids에는 요약 전체에 사용한 ID만 넣는다. "
                        "URL이나 ID를 새로 만들지 않는다.\n"
                        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response_body: dict[str, Any] | None = None
        for attempt in range(OPENAI_AI_SUMMARY_MAX_ATTEMPTS):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                    response_body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                should_retry = (
                    attempt + 1 < OPENAI_AI_SUMMARY_MAX_ATTEMPTS
                    and exc.code in OPENAI_AI_SUMMARY_RETRYABLE_HTTP_STATUS
                )
                if should_retry:
                    continue
                raise RuntimeError(f"OpenAI API HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError("OpenAI API connection failed") from exc

        if response_body is None:
            raise RuntimeError("OpenAI API response unavailable")

        response_status = str(response_body.get("status") or "").strip().lower()
        if response_status == "incomplete":
            details = response_body.get("incomplete_details")
            reason = str(details.get("reason") or "unknown") if isinstance(details, dict) else "unknown"
            if reason == "max_output_tokens":
                raise OpenAIExplanationResponseError(
                    "출력 토큰 한도에 도달해 응답이 완료되지 않았습니다."
                )
            raise OpenAIExplanationResponseError("OpenAI 응답이 완료되지 않았습니다.")

        output_text = extract_response_text(response_body)
        if not output_text.strip():
            raise OpenAIExplanationResponseError("OpenAI 응답에 출력 내용이 없습니다.")
        return parse_json_object(output_text)


def openai_client_from_env() -> OpenAIResponsesExplanationClient | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAIResponsesExplanationClient(api_key)


def openai_model_from_env(default: str = DEFAULT_OPENAI_MODEL) -> str:
    return os.environ.get("OPENAI_MODEL", default)


def extract_response_text(response_body: dict[str, Any]) -> str:
    if response_body.get("output_text"):
        return str(response_body["output_text"])

    parts: list[str] = []
    for item in response_body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    return "\n".join(parts).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("AI response is not a JSON object")
    return parsed


def _unique_strings(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
