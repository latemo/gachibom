"""LLM-backed help chatbot for the Jeju Maeum web app."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Protocol

from src.recommendation_service import (
    DEFAULT_OPENAI_MODEL,
    OPENAI_RESPONSES_URL,
    extract_response_text,
    parse_json_object,
)


HELP_CHATBOT_MAX_QUESTION_LENGTH = 700
HELP_CHATBOT_MAX_HISTORY_ITEMS = 8
HELP_CHATBOT_MAX_HISTORY_TEXT_LENGTH = 500
HELP_CHATBOT_TIMEOUT_SECONDS = 20

HELP_CHATBOT_SAFETY_NOTE = (
    "이 도움말은 의료 판단이나 여행 가능성을 보장하지 않습니다. 현장 접근성은 날씨, 운영 상황, 공사, "
    "혼잡도에 따라 달라질 수 있으므로 방문 전 공식 정보와 현장 문의를 확인해 주세요."
)

HELP_CHATBOT_TEXT_FORMAT = {
    "type": "json_schema",
    "name": "jeju_maeum_help_chatbot_reply",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "followups", "handoff_checklist"],
        "properties": {
            "answer": {"type": "string"},
            "followups": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 3,
            },
            "handoff_checklist": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
            },
        },
    },
}

HELP_CHATBOT_PRODUCT_CONTEXT = {
    "service_name": "가치봄 제주",
    "positioning": "제주 관광약자를 위한 무장애 여행 판단 보조 서비스",
    "does": [
        "사용자의 이동 조건을 정리한다.",
        "접근성 장소와 코스의 적합도를 설명한다.",
        "추천 이유, 감점 이유, 방문 전 확인 항목을 안내한다.",
        "출처, 정보 상태, 안전 안내를 함께 보여준다.",
    ],
    "does_not": [
        "의료 판단",
        "치료 효과 안내",
        "이동 가능성 보장",
        "실시간 현장 상태 보장",
        "개인 건강정보 장기 저장",
    ],
    "help_topics": [
        "처음 사용하는 방법",
        "점수와 등급 해석",
        "휠체어 접근 확인",
        "음식 제한 안내",
        "실제 경로 보기",
        "출처와 최신성",
        "개인정보와 건강정보",
        "API 또는 화면 실패",
        "운영자 검수 항목",
    ],
    "safety_note": HELP_CHATBOT_SAFETY_NOTE,
}


class HelpChatbotClient(Protocol):
    def generate_reply(self, context: dict[str, Any], *, model: str) -> dict[str, Any]:
        """Return a Korean help-chatbot response object."""


def build_help_chatbot_reply(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    model: str = DEFAULT_OPENAI_MODEL,
    client: HelpChatbotClient | None = None,
) -> dict[str, Any]:
    normalized_question = normalize_help_question(question)
    normalized_history = normalize_help_history(history or [])
    if client is None:
        return {
            "status": "disabled_no_key",
            "model": model,
            "answer": (
                "LLM 도움말 답변을 사용하려면 서버 실행 환경에 OPENAI_API_KEY가 필요합니다. "
                "현재는 브라우저의 기본 도움말만 사용할 수 있습니다."
            ),
            "followups": ["처음 사용하는 방법", "점수와 등급 읽는 법", "개인정보는 저장되나요?"],
            "handoff_checklist": ["OPENAI_API_KEY 설정", "추천 API 서버로 페이지 열기", "/api/help-chat 상태 확인"],
            "safety_note": HELP_CHATBOT_SAFETY_NOTE,
        }

    context = {
        "question": normalized_question,
        "recent_messages": normalized_history,
        "product_context": HELP_CHATBOT_PRODUCT_CONTEXT,
    }
    try:
        generated = client.generate_reply(context, model=model)
    except Exception as exc:
        return {
            "status": "error",
            "model": model,
            "answer": f"LLM 도움말 답변 생성에 실패했습니다: {exc.__class__.__name__}",
            "followups": ["처음 사용하는 방법", "화면 오류가 날 때", "방문 전 확인 항목"],
            "handoff_checklist": ["잠시 후 다시 시도", "질문을 한 문장으로 줄여 재입력", "공식 정보와 현장 문의 확인"],
            "safety_note": HELP_CHATBOT_SAFETY_NOTE,
        }

    return normalize_help_chatbot_reply(generated, model)


def normalize_help_question(value: Any) -> str:
    text = clean_help_text(value, HELP_CHATBOT_MAX_QUESTION_LENGTH)
    if not text:
        raise ValueError("question is required")
    return text


def normalize_help_history(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in values[-HELP_CHATBOT_MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        content = clean_help_text(item.get("content"), HELP_CHATBOT_MAX_HISTORY_TEXT_LENGTH)
        if content:
            normalized.append({"role": role, "content": content})
    return normalized


def normalize_help_chatbot_reply(value: dict[str, Any], model: str) -> dict[str, Any]:
    answer = clean_help_text(value.get("answer"), 1200)
    if not answer:
        answer = "질문을 이해하지 못했습니다. 서비스 사용법, 접근성 확인, 출처, 개인정보 기준 중 하나로 다시 물어봐 주세요."
    return {
        "status": "success",
        "model": model,
        "answer": enforce_help_safety(answer),
        "followups": clean_help_text_list(value.get("followups"), 3, 80),
        "handoff_checklist": clean_help_text_list(value.get("handoff_checklist"), 4, 100),
        "safety_note": HELP_CHATBOT_SAFETY_NOTE,
    }


def clean_help_text_list(values: Any, limit: int, max_length: int) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_help_text(value, max_length)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
        if len(result) >= limit:
            break
    return result


def clean_help_text(value: Any, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    text = re.sub(r"(.)\1{8,}", r"\1\1\1", text)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def enforce_help_safety(text: str) -> str:
    replacements = (
        (r"100%\s*가능", "현장 확인이 필요"),
        (r"무조건\s*추천", "조건 확인 후 참고"),
        (r"누구나\s*갈\s*수\s*있(?:습니다|다)", "조건에 따라 방문 전 확인이 필요합니다"),
        (r"문제없이\s*이동", "이동 부담은 현장 확인이 필요"),
        (r"보장합니다", "보장할 수 없습니다"),
    )
    sanitized = text
    for pattern, replacement in replacements:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized


class OpenAIResponsesHelpChatbotClient:
    def __init__(self, api_key: str, *, timeout_seconds: int = HELP_CHATBOT_TIMEOUT_SECONDS) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def generate_reply(self, context: dict[str, Any], *, model: str) -> dict[str, Any]:
        request_body = {
            "model": model,
            "reasoning": {"effort": "low"},
            "store": False,
            "text": {"format": HELP_CHATBOT_TEXT_FORMAT},
            "max_output_tokens": 900,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "너는 가치봄 제주 서비스의 도움말 챗봇이다. "
                        "서비스 사용법, 접근성 정보 해석, 방문 전 확인, 개인정보 기준을 한국어로 답한다. "
                        "의료 판단, 치료 효과, 이동 가능성 보장, 실시간 현장 상태 보장은 하지 않는다. "
                        "제공된 서비스 맥락 밖의 사실을 지어내지 말고, 모르면 확인 방법을 안내한다. "
                        "사용자의 이름, 연락처, 병원명, 상세 진단명 입력을 요구하지 않는다."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "아래 사용자 질문에 답하라. answer는 6문장 이내로 작성하고, "
                        "필요하면 followups에 사용자가 이어서 물어볼 만한 짧은 질문을 넣어라. "
                        "handoff_checklist에는 사용자가 실제로 확인할 항목만 넣어라. "
                        "반환 형식은 answer 문자열, followups 문자열 배열, handoff_checklist 문자열 배열이다.\n"
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

        return parse_json_object(extract_response_text(response_body))


def openai_help_chatbot_client_from_env() -> OpenAIResponsesHelpChatbotClient | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAIResponsesHelpChatbotClient(api_key)
