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
from src.rag_retrieval import retrieve_place_candidates
from src.scoring import build_recommendation_result, rank_places


TRAVELER_SUMMARY_KEYS = (
    "traveler_type",
    "mobility_conditions",
    "preferred_themes",
    "required_accessibility",
    "avoid",
)


DEFAULT_OPENAI_MODEL = "gpt-5-mini"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
AI_HEADLINE_MAX_LENGTH = 80
AI_LIST_ITEM_MAX_LENGTH = 100
CLOSED_SERVICE_STATUSES = frozenset({"permanently_closed", "temporarily_closed"})
RAG_RETRIEVAL_LIMIT = 12
RAG_RETRIEVER_NAME = "deterministic_bm25_structured_v1"


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
                "items": {"type": "string"},
                "maxItems": 4,
            },
            "cautions": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
            },
            "next_checks": {
                "type": "array",
                "items": {"type": "string"},
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
    open_candidates = [place for place in places if _is_open_service_candidate(place)]
    candidate_places = open_candidates
    retrieval_hits: list[dict[str, Any]] = []
    retrieval_status = "not_requested"
    data_gaps: list[str] = []

    if query_text:
        resource_types = query_intent.get("resource_types", [])
        if resource_types:
            retrieval_status = "resource_data_gap"
            data_gaps = list(resource_types)
            candidate_places = []
        else:
            retrieval_hits = retrieve_place_candidates(
                open_candidates,
                query=query_text,
                intent=_retrieval_constraints(query_intent),
                limit=max(RAG_RETRIEVAL_LIMIT, safe_limit * 4),
                as_of=today,
            )
            candidate_places = [hit["place"] for hit in retrieval_hits]
            retrieval_status = "applied" if candidate_places else "no_match"

    place_index = {place.get("id", ""): place for place in candidate_places}
    scores = rank_places(candidate_places, normalized_summary, limit=safe_limit, today=today)
    recommendation = build_recommendation_result(
        scores,
        normalized_summary,
        safety_notice=SAFETY_NOTICE,
        title="맞춤 접근성 추천 코스",
    )
    if retrieval_status in {"resource_data_gap", "no_match"}:
        recommendation["course"]["route"] = []
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


def _retrieval_constraints(query_intent: dict[str, Any]) -> dict[str, Any]:
    """Use only coarse, high-confidence fields as retrieval hard filters."""

    return {
        "regions": query_intent.get("regions", []),
        "categories": query_intent.get("categories", []),
    }


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
        return empty_ai_summary("skipped", ai_model, "요청에서 AI 설명 생성을 끄도록 지정했습니다.")
    if explanation_client is None:
        return empty_ai_summary("disabled_no_key", ai_model, "OPENAI_API_KEY가 설정되지 않아 로컬 점수 근거만 사용했습니다.")

    context = ai_prompt_context(recommendation, places, traveler_summary, retrieval=retrieval)
    try:
        generated = explanation_client.generate_summary(context, model=ai_model)
    except Exception as exc:
        return empty_ai_summary("error", ai_model, f"AI 설명 생성 실패: {exc.__class__.__name__}")

    return normalize_ai_summary(
        generated,
        ai_model,
        evidence_index=_retrieval_evidence_index(retrieval),
    )


def empty_ai_summary(status: str, model: str, note: str) -> dict[str, Any]:
    return {
        "status": status,
        "model": model,
        "headline": "",
        "rationale": [],
        "cautions": [],
        "next_checks": [],
        "citations": [],
        "note": note,
    }


def normalize_ai_summary(
    value: dict[str, Any],
    model: str,
    *,
    evidence_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": "success",
        "model": model,
        "headline": clean_ai_text(value.get("headline") or "조건에 맞춘 접근성 추천입니다.", AI_HEADLINE_MAX_LENGTH),
        "rationale": clean_ai_text_list(value.get("rationale", []))[:4],
        "cautions": clean_ai_text_list(value.get("cautions", []))[:4],
        "next_checks": clean_ai_text_list(value.get("next_checks", []))[:4],
        "citations": _resolve_ai_citations(value.get("evidence_ids"), evidence_index or {}),
        "note": clean_ai_text(value.get("note") or "", AI_LIST_ITEM_MAX_LENGTH),
    }


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
            "evidence": list(_retrieval_evidence_index(retrieval).values())[:8],
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


def _retrieval_evidence_index(
    retrieval: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(retrieval, dict):
        return index
    for match in retrieval.get("matches") or []:
        if not isinstance(match, dict):
            continue
        spot_id = str(match.get("spot_id") or "")
        evidence = match.get("evidence_bundle")
        if not isinstance(evidence, dict):
            continue
        verification = evidence.get("verification") if isinstance(evidence.get("verification"), dict) else {}
        for source in evidence.get("sources") or []:
            if not isinstance(source, dict):
                continue
            evidence_id = str(source.get("evidence_id") or "")
            source_url = str(source.get("url") or "")
            if not evidence_id or not source_url.startswith(("https://", "http://")):
                continue
            index[evidence_id] = {
                "evidence_id": evidence_id,
                "spot_id": spot_id,
                "source_title": str(source.get("title") or "")[:240],
                "source_url": source_url[:2048],
                "checked_at": source.get("checked_at") or verification.get("checked_at"),
                "verification_status": source.get("status") or verification.get("status") or "needs_check",
            }
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


class OpenAIResponsesExplanationClient:
    def __init__(self, api_key: str, *, timeout_seconds: int = 20) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def generate_summary(self, context: dict[str, Any], *, model: str) -> dict[str, Any]:
        request_body = {
            "model": model,
            "reasoning": {"effort": "low"},
            "store": False,
            "text": {"format": AI_SUMMARY_TEXT_FORMAT},
            "max_output_tokens": 900,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "너는 제주 접근성 여행 추천 서비스의 설명 생성기다. "
                        "의료 판단이나 방문 가능 보장을 하지 말고, 제공된 점수와 근거만 사용한다. "
                        "장소가 안전하다고 단정하지 말고, 점수·시설·검수 상태를 근거로 설명한다. "
                        "검색 근거를 언급할 때는 retrieval.evidence에 있는 evidence_id만 사용한다. "
                        "모든 문장은 한국어로 작성한다."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "다음 추천 결과를 접근성 여행자가 바로 이해할 수 있게 요약하라. "
                        "headline은 35자 안팎의 차분한 한 문장으로 쓴다. "
                        "rationale에는 선택 조건과 장소 근거가 어떻게 연결되는지 쓴다. "
                        "cautions에는 현장 변수, 운영 여부, 혼잡, 음식 제한, 날씨 민감 요소처럼 확정할 수 없는 부분을 쓴다. "
                        "next_checks에는 방문 전 실제로 확인할 항목만 쓴다. "
                        "새로운 장소명, 없는 시설, 의학적 조언은 만들지 않는다. "
                        "evidence_ids에는 실제 설명에 사용한 retrieval.evidence의 ID만 넣고, "
                        "근거가 없으면 빈 배열로 둔다. URL이나 ID를 새로 만들지 않는다. "
                        "반환 형식은 headline 문자열, rationale 문자열 배열, cautions 문자열 배열, "
                        "next_checks 문자열 배열, evidence_ids 문자열 배열이다.\n"
                        + json.dumps(context, ensure_ascii=False)
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenAI API HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenAI API connection failed") from exc

        output_text = extract_response_text(response_body)
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
