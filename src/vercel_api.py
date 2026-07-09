"""Vercel Python function adapters for the recommendation API."""

from __future__ import annotations

import json
import os
from datetime import date
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.help_chatbot_service import build_help_chatbot_reply, openai_help_chatbot_client_from_env
from src.place_locations import load_place_location_index
from src.recommendation_api import (
    DEFAULT_LOCATION_OVERRIDES_PATH,
    DEFAULT_PLACES_PATH,
    DEFAULT_ROADVIEW_METADATA_PATH,
    DEFAULT_TOURISM_WEAK_COURSES_PATH,
    MAX_REQUEST_BODY_BYTES,
    ApiRequestError,
    fetch_route_directions,
    load_places,
    parse_bool,
    parse_help_chat_question,
    parse_limit,
    parse_model,
    parse_route_points,
)
from src.recommendation_service import (
    DEFAULT_OPENAI_MODEL,
    build_runtime_recommendation,
    openai_client_from_env,
    openai_model_from_env,
)
from src.tourism_weak_courses import augment_places_with_tourism_weak_courses, load_tourism_weak_courses


@lru_cache(maxsize=1)
def runtime_state() -> dict[str, Any]:
    places = load_places(DEFAULT_PLACES_PATH)
    course_dataset = (
        load_tourism_weak_courses(DEFAULT_TOURISM_WEAK_COURSES_PATH)
        if DEFAULT_TOURISM_WEAK_COURSES_PATH.exists()
        else {}
    )
    places = augment_places_with_tourism_weak_courses(places, course_dataset)
    location_index = load_place_location_index(
        places,
        roadview_metadata_path=DEFAULT_ROADVIEW_METADATA_PATH,
        overrides_path=DEFAULT_LOCATION_OVERRIDES_PATH,
    )
    return {
        "places": places,
        "location_index": location_index,
        "tourism_weak_course_summary": course_dataset.get("summary", {}) if course_dataset else {},
    }


def build_health_payload() -> dict[str, Any]:
    state = runtime_state()
    return {
        "status": "ok",
        "service": "jeju-maeum-recommendation-api",
        "runtime": "vercel-python",
        "ai_model": openai_model_from_env(DEFAULT_OPENAI_MODEL),
        "openai_api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "places": len(state["places"]),
        "features": {
            "route_proxy": True,
            "help_chatbot": True,
            "tourism_weak_courses": bool(state["tourism_weak_course_summary"]),
        },
        "tourism_weak_courses": state["tourism_weak_course_summary"],
    }


def handle_health(request: BaseHTTPRequestHandler) -> None:
    send_json(request, build_health_payload())


def handle_recommendations(request: BaseHTTPRequestHandler) -> None:
    try:
        payload = read_json_body(request)
        state = runtime_state()
        traveler_summary = payload.get("traveler_summary") or payload.get("profile") or {}
        limit = parse_limit(payload.get("limit", 4))
        use_ai = parse_bool(payload.get("use_ai", True))
        model = parse_model(payload.get("model") or openai_model_from_env(DEFAULT_OPENAI_MODEL))
        client = openai_client_from_env() if use_ai else None
        result = build_runtime_recommendation(
            state["places"],
            traveler_summary,
            today=generated_at(),
            limit=limit,
            use_ai=use_ai,
            ai_model=model,
            explanation_client=client,
            location_index=state["location_index"],
        )
    except ApiRequestError as exc:
        send_error_json(request, exc.code, str(exc), status=exc.status)
        return
    except json.JSONDecodeError:
        send_error_json(request, "invalid_json", "잘못된 JSON 요청입니다.", status=HTTPStatus.BAD_REQUEST)
        return
    except Exception as exc:
        send_error_json(
            request,
            "recommendation_failed",
            f"추천 생성 실패: {exc.__class__.__name__}",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        return

    send_json(request, result)


def handle_help_chat(request: BaseHTTPRequestHandler) -> None:
    try:
        payload = read_json_body(request)
        question = parse_help_chat_question(payload.get("question") or payload.get("message"))
        use_ai = parse_bool(payload.get("use_ai", True))
        model = parse_model(payload.get("model") or openai_model_from_env(DEFAULT_OPENAI_MODEL))
        client = openai_help_chatbot_client_from_env() if use_ai else None
        result = build_help_chatbot_reply(
            question,
            history=payload.get("history") or payload.get("messages") or [],
            model=model,
            client=client,
        )
    except ApiRequestError as exc:
        send_error_json(request, exc.code, str(exc), status=exc.status)
        return
    except json.JSONDecodeError:
        send_error_json(request, "invalid_json", "잘못된 JSON 요청입니다.", status=HTTPStatus.BAD_REQUEST)
        return
    except Exception as exc:
        send_error_json(
            request,
            "help_chat_failed",
            f"도움말 답변 실패: {exc.__class__.__name__}",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        return

    send_json(request, result)


def handle_routes(request: BaseHTTPRequestHandler) -> None:
    try:
        payload = read_json_body(request)
        points = parse_route_points(payload.get("points") or payload.get("route") or [])
        result = fetch_route_directions(points)
    except ApiRequestError as exc:
        send_error_json(request, exc.code, str(exc), status=exc.status)
        return
    except json.JSONDecodeError:
        send_error_json(request, "invalid_json", "잘못된 JSON 요청입니다.", status=HTTPStatus.BAD_REQUEST)
        return
    except Exception as exc:
        send_error_json(
            request,
            "route_failed",
            f"경로 계산 실패: {exc.__class__.__name__}",
            status=HTTPStatus.BAD_GATEWAY,
        )
        return

    send_json(request, result)


def read_json_body(request: BaseHTTPRequestHandler) -> dict[str, Any]:
    try:
        content_length = int(request.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ApiRequestError("Content-Length 헤더가 올바르지 않습니다.", code="invalid_content_length") from exc
    if content_length <= 0:
        return {}
    if content_length > MAX_REQUEST_BODY_BYTES:
        raise ApiRequestError(
            "요청 본문이 너무 큽니다.",
            status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            code="request_body_too_large",
        )
    raw = request.rfile.read(content_length)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("JSON object required", raw.decode("utf-8"), 0)
    return payload


def generated_at() -> date:
    raw = os.environ.get("GENERATED_AT", "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return date.today()


def handle_options(request: BaseHTTPRequestHandler) -> None:
    request.send_response(HTTPStatus.NO_CONTENT)
    add_common_headers(request)
    request.end_headers()


def method_not_allowed(request: BaseHTTPRequestHandler) -> None:
    send_error_json(request, "method_not_allowed", "지원하지 않는 HTTP 메서드입니다.", status=HTTPStatus.METHOD_NOT_ALLOWED)


def send_error_json(request: BaseHTTPRequestHandler, code: str, message: str, *, status: HTTPStatus) -> None:
    send_json(request, {"error": message, "code": code}, status=status)


def send_json(request: BaseHTTPRequestHandler, value: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    request.send_response(status)
    add_common_headers(request)
    request.send_header("Content-Type", "application/json; charset=utf-8")
    request.send_header("Cache-Control", "no-store")
    request.send_header("Content-Length", str(len(body)))
    request.end_headers()
    request.wfile.write(body)


def add_common_headers(request: BaseHTTPRequestHandler) -> None:
    request.send_header("Access-Control-Allow-Origin", "*")
    request.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    request.send_header("Access-Control-Allow-Headers", "Content-Type")
