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


AI_SUMMARY_TEXT_FORMAT = {
    "type": "json_schema",
    "name": "jeju_accessible_travel_summary",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["headline", "rationale", "cautions", "next_checks"],
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
    limit: int = 4,
    use_ai: bool = True,
    ai_model: str = DEFAULT_OPENAI_MODEL,
    explanation_client: RecommendationExplanationClient | None = None,
    location_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_summary = normalize_traveler_summary(traveler_summary)
    safe_limit = max(1, min(int(limit or 4), 4))
    candidate_places = [place for place in places if _is_open_service_candidate(place)]
    place_index = {place.get("id", ""): place for place in candidate_places}
    scores = rank_places(candidate_places, normalized_summary, limit=safe_limit, today=today)
    recommendation = build_recommendation_result(
        scores,
        normalized_summary,
        safety_notice=SAFETY_NOTICE,
        title="맞춤 접근성 추천 코스",
    )
    result_places = [
        app_place_result(score, place_index.get(score.spot_id, {}), location_index=location_index or {})
        for score in scores
    ]
    ai_summary = build_ai_summary(
        recommendation,
        result_places,
        normalized_summary,
        use_ai=use_ai,
        ai_model=ai_model,
        explanation_client=explanation_client,
    )
    return {
        "generated_at": today.isoformat(),
        "engine": {
            "scoring": "local_accessibility_score_v1",
            "ai_model": ai_model,
            "ai_status": ai_summary["status"],
        },
        "traveler_summary": normalized_summary,
        "recommendation": recommendation,
        "places": result_places,
        "ai_summary": ai_summary,
        "safety_notice": SAFETY_NOTICE,
    }


def _is_open_service_candidate(place: dict[str, Any]) -> bool:
    visit_info = place.get("visit_info")
    if not isinstance(visit_info, dict):
        return True
    return visit_info.get("service_status") not in CLOSED_SERVICE_STATUSES


def build_ai_summary(
    recommendation: dict[str, Any],
    places: list[dict[str, Any]],
    traveler_summary: dict[str, list[str]],
    *,
    use_ai: bool,
    ai_model: str,
    explanation_client: RecommendationExplanationClient | None,
) -> dict[str, Any]:
    if not use_ai:
        return empty_ai_summary("skipped", ai_model, "요청에서 AI 설명 생성을 끄도록 지정했습니다.")
    if explanation_client is None:
        return empty_ai_summary("disabled_no_key", ai_model, "OPENAI_API_KEY가 설정되지 않아 로컬 점수 근거만 사용했습니다.")

    context = ai_prompt_context(recommendation, places, traveler_summary)
    try:
        generated = explanation_client.generate_summary(context, model=ai_model)
    except Exception as exc:
        return empty_ai_summary("error", ai_model, f"AI 설명 생성 실패: {exc.__class__.__name__}")

    return normalize_ai_summary(generated, ai_model)


def empty_ai_summary(status: str, model: str, note: str) -> dict[str, Any]:
    return {
        "status": status,
        "model": model,
        "headline": "",
        "rationale": [],
        "cautions": [],
        "next_checks": [],
        "note": note,
    }


def normalize_ai_summary(value: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "status": "success",
        "model": model,
        "headline": clean_ai_text(value.get("headline") or "조건에 맞춘 접근성 추천입니다.", AI_HEADLINE_MAX_LENGTH),
        "rationale": clean_ai_text_list(value.get("rationale", []))[:4],
        "cautions": clean_ai_text_list(value.get("cautions", []))[:4],
        "next_checks": clean_ai_text_list(value.get("next_checks", []))[:4],
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
) -> dict[str, Any]:
    return {
        "traveler_summary": traveler_summary,
        "course": recommendation.get("course", {}),
        "score": recommendation.get("score", {}),
        "fit_reasons": recommendation.get("fit_reasons", [])[:8],
        "deduction_reasons": recommendation.get("deduction_reasons", [])[:8],
        "check_before_visit": recommendation.get("check_before_visit", [])[:8],
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
                        "반환 형식은 headline 문자열, rationale 문자열 배열, cautions 문자열 배열, "
                        "next_checks 문자열 배열이다.\n"
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
