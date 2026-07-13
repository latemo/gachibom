"""HTTP server for the Jeju Maeum recommendation app."""

from __future__ import annotations

import json
import logging
from datetime import date
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.help_chatbot_service import build_help_chatbot_reply, openai_help_chatbot_client_from_env
from src.place_locations import load_place_location_index
from src.place_visit_info import enrich_places_with_visit_info
from src.recommendation_service import (
    DEFAULT_OPENAI_MODEL,
    build_runtime_recommendation,
    openai_client_from_env,
    openai_model_from_env,
)
from src.tourism_weak_courses import augment_places_with_tourism_weak_courses, load_tourism_weak_courses


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEB_DIR = ROOT / "web"
DEFAULT_PLACES_PATH = ROOT / "data" / "jeju_accessible_spots.json"
DEFAULT_ROADVIEW_METADATA_PATH = ROOT / "data" / "roadview_image_metadata.json"
DEFAULT_LOCATION_OVERRIDES_PATH = ROOT / "data" / "place_location_overrides.json"
DEFAULT_TOURISM_WEAK_COURSES_PATH = ROOT / "data" / "tourism_weak_recommendation_courses.json"
DEFAULT_PLACE_CATALOG_PATH = ROOT / "data" / "place_catalog.roadview_facility.json"
DEFAULT_VISIT_INFO_OVERRIDES_PATH = ROOT / "data" / "place_visit_info_overrides.json"
MAX_REQUEST_BODY_BYTES = 1_000_000
MAX_ROUTE_POINTS = 8
ROUTE_PROVIDER_TIMEOUT_SECONDS = 7
MAX_HELP_CHAT_QUESTION_BYTES = 2_000


LOGGER = logging.getLogger(__name__)


class ApiRequestError(ValueError):
    def __init__(self, message: str, *, status: HTTPStatus = HTTPStatus.BAD_REQUEST, code: str = "bad_request") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def load_places(path: Path = DEFAULT_PLACES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json_list(path: Path, *, label: str = "optional data") -> list[dict[str, Any]]:
    """Load an optional JSON object array without blocking service startup."""

    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        LOGGER.warning(
            "%s could not be loaded from %s (%s); continuing without it",
            label,
            path,
            exc.__class__.__name__,
        )
        return []
    if not isinstance(value, list):
        LOGGER.warning("%s at %s is not a JSON array; continuing without it", label, path)
        return []

    rows = [item for item in value if isinstance(item, dict)]
    if len(rows) != len(value):
        LOGGER.warning(
            "%s at %s contains %d non-object row(s); ignoring those rows",
            label,
            path,
            len(value) - len(rows),
        )
    return rows


class RecommendationApiHandler(SimpleHTTPRequestHandler):
    places: list[dict[str, Any]] = []
    location_index: dict[str, dict[str, Any]] = {}
    tourism_weak_course_summary: dict[str, Any] = {}
    generated_at: date = date.today()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/health", "/api/health"}:
            self.send_json(
                {
                    "status": "ok",
                    "service": "jeju-maeum-recommendation-api",
                    "ai_model": openai_model_from_env(DEFAULT_OPENAI_MODEL),
                    "places": len(self.places),
                    "features": {
                        "route_proxy": True,
                        "help_chatbot": True,
                        "tourism_weak_courses": bool(self.tourism_weak_course_summary),
                    },
                    "tourism_weak_courses": self.tourism_weak_course_summary,
                }
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/recommendations":
            self.handle_recommendations()
            return
        if path == "/api/routes":
            self.handle_routes()
            return
        if path == "/api/help-chat":
            self.handle_help_chat()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def handle_recommendations(self) -> None:
        try:
            payload = self.read_json_body()
            traveler_summary = payload.get("traveler_summary") or payload.get("profile") or {}
            limit = parse_limit(payload.get("limit", 4))
            use_ai = parse_bool(payload.get("use_ai", True))
            model = parse_model(payload.get("model") or openai_model_from_env(DEFAULT_OPENAI_MODEL))
            client = openai_client_from_env() if use_ai else None
            result = build_runtime_recommendation(
                self.places,
                traveler_summary,
                today=self.generated_at,
                limit=limit,
                use_ai=use_ai,
                ai_model=model,
                explanation_client=client,
                location_index=self.location_index,
            )
        except ApiRequestError as exc:
            self.send_error_json(exc.code, str(exc), status=exc.status)
            return
        except json.JSONDecodeError:
            self.send_error_json("invalid_json", "잘못된 JSON 요청입니다.", status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self.send_error_json(
                "recommendation_failed",
                f"추천 생성 실패: {exc.__class__.__name__}",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self.send_json(result)

    def handle_help_chat(self) -> None:
        try:
            payload = self.read_json_body()
            question = parse_help_chat_question(payload.get("question") or payload.get("message"))
            use_ai = parse_bool(payload.get("use_ai", True))
            model = parse_model(payload.get("model") or openai_model_from_env(DEFAULT_OPENAI_MODEL))
            client = openai_help_chatbot_client_from_env() if use_ai else None
            result = build_help_chatbot_reply(
                question,
                history=payload.get("history") or payload.get("messages") or [],
                recommendation_context=payload.get("recommendation_context"),
                model=model,
                client=client,
            )
        except ApiRequestError as exc:
            self.send_error_json(exc.code, str(exc), status=exc.status)
            return
        except json.JSONDecodeError:
            self.send_error_json("invalid_json", "잘못된 JSON 요청입니다.", status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self.send_error_json(
                "help_chat_failed",
                f"도움말 답변 실패: {exc.__class__.__name__}",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self.send_json(result)

    def handle_routes(self) -> None:
        try:
            payload = self.read_json_body()
            points = parse_route_points(payload.get("points") or payload.get("route") or [])
            result = fetch_route_directions(points)
        except ApiRequestError as exc:
            self.send_error_json(exc.code, str(exc), status=exc.status)
            return
        except json.JSONDecodeError:
            self.send_error_json("invalid_json", "잘못된 JSON 요청입니다.", status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self.send_error_json(
                "route_failed",
                f"경로 계산 실패: {exc.__class__.__name__}",
                status=HTTPStatus.BAD_GATEWAY,
            )
            return

        self.send_json(result)

    def read_json_body(self) -> dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
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
        raw = self.rfile.read(content_length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise json.JSONDecodeError("JSON object required", raw.decode("utf-8"), 0)
        return payload

    def send_error_json(self, code: str, message: str, *, status: HTTPStatus) -> None:
        self.send_json({"error": message, "code": code}, status=status)

    def send_json(self, value: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiRequestError("limit은 숫자여야 합니다.", code="invalid_limit") from exc
    if limit < 1:
        raise ApiRequestError("limit은 1 이상이어야 합니다.", code="invalid_limit")
    return min(limit, 4)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def parse_model(value: Any) -> str:
    model = str(value or "").strip()
    if not model:
        return DEFAULT_OPENAI_MODEL
    if len(model) > 80 or not all(char.isalnum() or char in {".", "-", "_"} for char in model):
        raise ApiRequestError("model 값이 올바르지 않습니다.", code="invalid_model")
    return model


def parse_help_chat_question(value: Any) -> str:
    question = str(value or "").strip()
    if not question:
        raise ApiRequestError("question은 비어 있을 수 없습니다.", code="missing_question")
    if len(question.encode("utf-8")) > MAX_HELP_CHAT_QUESTION_BYTES:
        raise ApiRequestError(
            "question이 너무 깁니다.",
            status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            code="question_too_large",
        )
    return question


def parse_route_points(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ApiRequestError("points는 배열이어야 합니다.", code="invalid_route_points")
    if len(value) < 2:
        raise ApiRequestError("경로 계산에는 두 곳 이상의 좌표가 필요합니다.", code="not_enough_route_points")
    if len(value) > MAX_ROUTE_POINTS:
        raise ApiRequestError(f"경로 좌표는 최대 {MAX_ROUTE_POINTS}곳까지 가능합니다.", code="too_many_route_points")

    points: list[dict[str, Any]] = []
    for index, point in enumerate(value, start=1):
        if not isinstance(point, dict):
            raise ApiRequestError(f"{index}번 좌표가 올바르지 않습니다.", code="invalid_route_point")
        try:
            latitude = float(point["latitude"])
            longitude = float(point["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiRequestError(f"{index}번 좌표의 위도/경도가 올바르지 않습니다.", code="invalid_route_coordinate") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ApiRequestError(f"{index}번 좌표 범위가 올바르지 않습니다.", code="invalid_route_coordinate")
        points.append(
            {
                "name": str(point.get("name") or f"{index}번 장소")[:80],
                "spot_id": str(point.get("spot_id") or "")[:120],
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return points


def fetch_route_directions(points: list[dict[str, Any]]) -> dict[str, Any]:
    coordinates = ";".join(f"{point['longitude']:.7f},{point['latitude']:.7f}" for point in points)
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{coordinates}?overview=full&geometries=geojson&steps=false"
    )
    request = Request(url, headers={"User-Agent": "jeju-maeum-accessible-travel/1.0"})
    try:
        with urlopen(request, timeout=ROUTE_PROVIDER_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ApiRequestError("경로 제공자가 응답하지 않았습니다.", status=HTTPStatus.BAD_GATEWAY, code="route_provider_error") from exc
    except (URLError, TimeoutError) as exc:
        raise ApiRequestError("경로 제공자 연결에 실패했습니다.", status=HTTPStatus.BAD_GATEWAY, code="route_provider_unavailable") from exc

    route = (payload.get("routes") or [None])[0]
    coordinates_payload = route.get("geometry", {}).get("coordinates") if isinstance(route, dict) else None
    if not isinstance(route, dict) or not isinstance(coordinates_payload, list) or len(coordinates_payload) < 2:
        raise ApiRequestError("사용 가능한 경로를 찾지 못했습니다.", status=HTTPStatus.BAD_GATEWAY, code="route_not_found")

    return {
        "provider": "osrm_public_route_proxy",
        "mode": "driving",
        "distance_meters": route.get("distance"),
        "duration_seconds": route.get("duration"),
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates_payload,
        },
        "waypoints": [
            {
                "name": point["name"],
                "spot_id": point["spot_id"],
                "latitude": point["latitude"],
                "longitude": point["longitude"],
            }
            for point in points
        ],
    }


def create_server(
    *,
    host: str,
    port: int,
    web_dir: Path = DEFAULT_WEB_DIR,
    places_path: Path = DEFAULT_PLACES_PATH,
    roadview_metadata_path: Path = DEFAULT_ROADVIEW_METADATA_PATH,
    location_overrides_path: Path = DEFAULT_LOCATION_OVERRIDES_PATH,
    tourism_weak_courses_path: Path = DEFAULT_TOURISM_WEAK_COURSES_PATH,
    place_catalog_path: Path = DEFAULT_PLACE_CATALOG_PATH,
    visit_info_overrides_path: Path = DEFAULT_VISIT_INFO_OVERRIDES_PATH,
    generated_at: date | None = None,
) -> ThreadingHTTPServer:
    handler_class = partial(RecommendationApiHandler, directory=str(web_dir))
    places = load_places(places_path)
    course_dataset = load_tourism_weak_courses(tourism_weak_courses_path) if tourism_weak_courses_path.exists() else {}
    places = augment_places_with_tourism_weak_courses(places, course_dataset)
    catalog_rows = load_optional_json_list(place_catalog_path, label="place catalog")
    reviewed_rows = load_optional_json_list(
        visit_info_overrides_path, label="reviewed visit information"
    )
    places = enrich_places_with_visit_info(places, catalog_rows, reviewed_rows)
    RecommendationApiHandler.places = places
    RecommendationApiHandler.tourism_weak_course_summary = course_dataset.get("summary", {}) if course_dataset else {}
    RecommendationApiHandler.location_index = load_place_location_index(
        places,
        roadview_metadata_path=roadview_metadata_path,
        overrides_path=location_overrides_path,
    )
    RecommendationApiHandler.generated_at = generated_at or date.today()
    return ThreadingHTTPServer((host, port), handler_class)


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8790,
    web_dir: Path = DEFAULT_WEB_DIR,
    places_path: Path = DEFAULT_PLACES_PATH,
    roadview_metadata_path: Path = DEFAULT_ROADVIEW_METADATA_PATH,
    location_overrides_path: Path = DEFAULT_LOCATION_OVERRIDES_PATH,
    tourism_weak_courses_path: Path = DEFAULT_TOURISM_WEAK_COURSES_PATH,
    place_catalog_path: Path = DEFAULT_PLACE_CATALOG_PATH,
    visit_info_overrides_path: Path = DEFAULT_VISIT_INFO_OVERRIDES_PATH,
    generated_at: date | None = None,
) -> None:
    server = create_server(
        host=host,
        port=port,
        web_dir=web_dir,
        places_path=places_path,
        roadview_metadata_path=roadview_metadata_path,
        location_overrides_path=location_overrides_path,
        tourism_weak_courses_path=tourism_weak_courses_path,
        place_catalog_path=place_catalog_path,
        visit_info_overrides_path=visit_info_overrides_path,
        generated_at=generated_at,
    )
    with server:
        print(f"jeju_maeum_api=http://{host}:{port}")
        print(f"places={len(RecommendationApiHandler.places)}")
        print(f"locations={len(RecommendationApiHandler.location_index)}")
        print(f"tourism_weak_course_matches={RecommendationApiHandler.tourism_weak_course_summary.get('matched_places', 0)}")
        print(f"ai_model={openai_model_from_env(DEFAULT_OPENAI_MODEL)}")
        server.serve_forever()
