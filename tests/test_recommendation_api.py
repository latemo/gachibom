import http.client
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from src.recommendation_api import MAX_REQUEST_BODY_BYTES, create_server, load_optional_json_list
from src.vercel_api import handle_help_chat as handle_vercel_help_chat


ROOT = Path(__file__).resolve().parents[1]


class OptionalJsonListTests(unittest.TestCase):
    def test_missing_file_is_empty_without_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.json"

            self.assertEqual(load_optional_json_list(path, label="place catalog"), [])

    def test_invalid_json_and_non_array_fail_open_with_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.json"
            invalid_path.write_text("{bad", encoding="utf-8")
            invalid_encoding_path = Path(temp_dir) / "invalid-encoding.json"
            invalid_encoding_path.write_bytes(b"\xff\xfe")
            object_path = Path(temp_dir) / "object.json"
            object_path.write_text('{"items": []}', encoding="utf-8")

            with self.assertLogs("src.recommendation_api", level="WARNING") as logs:
                self.assertEqual(load_optional_json_list(invalid_path, label="place catalog"), [])
                self.assertEqual(load_optional_json_list(invalid_encoding_path, label="place catalog"), [])
                self.assertEqual(load_optional_json_list(object_path, label="place catalog"), [])

            self.assertTrue(any("could not be loaded" in message for message in logs.output))
            self.assertTrue(any("is not a JSON array" in message for message in logs.output))

    def test_valid_array_keeps_only_object_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text('[{"catalog_id": "one"}, null, "invalid"]', encoding="utf-8")

            with self.assertLogs("src.recommendation_api", level="WARNING"):
                rows = load_optional_json_list(path, label="place catalog")

            self.assertEqual(rows, [{"catalog_id": "one"}])


class RecommendationApiContractTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(
            host="127.0.0.1",
            port=0,
            web_dir=ROOT / "web",
            places_path=ROOT / "data" / "jeju_accessible_spots.json",
            generated_at=date(2026, 7, 9),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        self.base_url = f"http://{self.host}:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_health_endpoint_returns_public_contract(self):
        with patch.dict("os.environ", {"OPENAI_MODEL": "gpt-5-mini"}, clear=False):
            status, payload = self.get_json("/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "jeju-maeum-recommendation-api")
        self.assertEqual(payload["ai_model"], "gpt-5-mini")
        self.assertGreater(payload["places"], 30)
        self.assertTrue(payload["features"]["help_chatbot"])

    def test_server_loads_manually_reviewed_visit_information(self):
        places = self.server.RequestHandlerClass.func.places
        bunker = next(place for place in places if place["id"] == "jeju_indoor_bunker_lumieres_010")

        self.assertEqual(
            bunker["visit_info"]["address"],
            "제주특별자치도 서귀포시 성산읍 서성일로1168번길 89-17",
        )
        self.assertEqual(bunker["visit_info"]["service_status"], "active")
        self.assertEqual(bunker["visit_info"]["last_verified_at"], "2026-07-13")
        self.assertTrue(bunker["visit_info"]["evidence"])

    def test_server_starts_when_optional_place_catalog_is_malformed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "catalog.json"
            catalog_path.write_text("{bad", encoding="utf-8")

            with self.assertLogs("src.recommendation_api", level="WARNING"):
                server = create_server(
                    host="127.0.0.1",
                    port=0,
                    web_dir=ROOT / "web",
                    places_path=ROOT / "data" / "jeju_accessible_spots.json",
                    place_catalog_path=catalog_path,
                    visit_info_overrides_path=Path(temp_dir) / "missing-reviewed.json",
                    generated_at=date(2026, 7, 9),
                )
            try:
                self.assertGreater(len(server.RequestHandlerClass.func.places), 30)
                self.assertTrue(
                    all(
                        place["visit_info"]["address"] is None
                        for place in server.RequestHandlerClass.func.places
                    )
                )
            finally:
                server.server_close()

    def test_recommendations_endpoint_returns_schema_valid_recommendation_without_ai(self):
        status, payload = self.post_json(
            "/api/recommendations",
            {
                "traveler_summary": {
                    "traveler_type": ["diet_restricted_traveler"],
                    "mobility_conditions": ["체력 저하"],
                    "preferred_themes": ["실내"],
                    "required_accessibility": ["장애인 화장실", "주차"],
                    "avoid": ["식당 제외"],
                },
                "limit": 4,
                "use_ai": False,
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["generated_at"], "2026-07-09")
        self.assertEqual(payload["engine"]["ai_status"], "skipped")
        self.assertLessEqual(len(payload["places"]), 4)
        self.assertFalse(any(place["location"] is None for place in payload["places"]))
        self.assertTrue(all(place["location"]["point_role"] for place in payload["places"]))
        self.assertTrue(all("visit_info" in place for place in payload["places"]))
        self.assertTrue(all(place["visit_info"]["verification_status"] == "needs_check" for place in payload["places"]))
        self.assertTrue(any(place["visit_info"]["address"] for place in payload["places"]))

        schema = json.loads((ROOT / "data" / "schemas" / "recommendation_result.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(payload["recommendation"])), [])

        seed_schema = json.loads(
            (ROOT / "data" / "schemas" / "app_recommendation_seed.schema.json").read_text(encoding="utf-8")
        )
        place_contract = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "#/$defs/placeResult",
            "$defs": seed_schema["$defs"],
        }
        place_validator = Draft202012Validator(place_contract)
        self.assertTrue(
            all(not list(place_validator.iter_errors(place)) for place in payload["places"])
        )

    def test_routes_endpoint_returns_proxy_route_with_mocked_provider(self):
        provider_payload = {
            "routes": [
                {
                    "distance": 12345.6,
                    "duration": 1900.0,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [126.5179884, 33.4813072],
                            [126.5902364, 33.2966815],
                        ],
                    },
                }
            ]
        }

        class FakeProviderResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(provider_payload).encode("utf-8")

        with patch("src.recommendation_api.urlopen", return_value=FakeProviderResponse()):
            status, payload = self.post_json(
                "/api/routes",
                {
                    "points": [
                        {"name": "제주문학관", "latitude": 33.4813072, "longitude": 126.5179884},
                        {"name": "제주한란전시관", "latitude": 33.2966815, "longitude": 126.5902364},
                    ]
                },
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["provider"], "osrm_public_route_proxy")
        self.assertEqual(payload["distance_meters"], 12345.6)
        self.assertEqual(len(payload["geometry"]["coordinates"]), 2)
        self.assertEqual(len(payload["waypoints"]), 2)

    def test_help_chat_endpoint_returns_llm_backed_reply_with_mocked_client(self):
        class FakeHelpClient:
            def __init__(self):
                self.context = None

            def generate_reply(self, context, *, model):
                self.context = context
                return {
                    "answer": f"{context['question']} 답변",
                    "followups": ["방문 전 확인은?"],
                    "handoff_checklist": ["공식 정보 확인"],
                }

        client = FakeHelpClient()
        with patch("src.recommendation_api.openai_help_chatbot_client_from_env", return_value=client):
            status, payload = self.post_json(
                "/api/help-chat",
                {
                    "question": "점수는 어떻게 읽나요?",
                    "recommendation_context": {
                        "mode": "runtime",
                        "selected_place": {
                            "spot_id": "spot-1",
                            "name": "제주문학관",
                            "score": {"total": 84, "grade": "B"},
                            "internal_note": "제외됨",
                        },
                    },
                },
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["model"], "gpt-5-mini")
        self.assertIn("점수는 어떻게 읽나요?", payload["answer"])
        recommendation_context = client.context["recommendation_context"]
        self.assertEqual(recommendation_context["selected_place"]["score"]["total"], 84)
        self.assertNotIn("internal_note", recommendation_context["selected_place"])

    def test_help_chat_endpoint_rejects_blank_question(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.post_json("/api/help-chat", {"question": "   "})

        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertEqual(payload["code"], "missing_question")

    def test_routes_endpoint_rejects_missing_points(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.post_json("/api/routes", {"points": []})

        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertEqual(payload["code"], "not_enough_route_points")

    def test_recommendations_endpoint_rejects_invalid_json(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.post_raw("/api/recommendations", b"{bad json", content_type="application/json")

        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertEqual(payload["code"], "invalid_json")

    def test_recommendations_endpoint_rejects_invalid_limit_as_client_error(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.post_json("/api/recommendations", {"limit": "많이", "use_ai": False})

        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertEqual(payload["code"], "invalid_limit")

    def test_recommendations_endpoint_rejects_oversized_body(self):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.putrequest("POST", "/api/recommendations")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(MAX_REQUEST_BODY_BYTES + 1))
        connection.endheaders()
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()

        self.assertEqual(response.status, 413)
        self.assertEqual(payload["code"], "request_body_too_large")

    def test_recommendations_endpoint_does_not_expose_internal_exception_text(self):
        with patch("src.recommendation_api.build_runtime_recommendation", side_effect=RuntimeError("secret-token-value")):
            with self.assertRaises(urllib.error.HTTPError) as context:
                self.post_json("/api/recommendations", {"use_ai": False})

        body = context.exception.read().decode("utf-8")
        payload = json.loads(body)
        self.assertEqual(context.exception.code, 500)
        self.assertEqual(payload["code"], "recommendation_failed")
        self.assertNotIn("secret-token-value", body)

    def get_json(self, path: str) -> tuple[int, dict]:
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        return self.post_raw(path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def post_raw(self, path: str, body: bytes, *, content_type: str = "application/json") -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))


class VercelHelpChatContractTests(unittest.TestCase):
    def test_vercel_adapter_passes_recommendation_context(self):
        class FakeHelpClient:
            def __init__(self):
                self.context = None

            def generate_reply(self, context, *, model):
                self.context = context
                return {"answer": "추천 근거 답변", "followups": [], "handoff_checklist": []}

        request_payload = {
            "question": "왜 이 장소가 추천됐나요?",
            "recommendation_context": {
                "mode": "runtime",
                "selected_place": {"spot_id": "spot-1", "name": "제주문학관"},
            },
        }
        request = FakeVercelRequest(request_payload)
        client = FakeHelpClient()

        with patch("src.vercel_api.openai_help_chatbot_client_from_env", return_value=client):
            handle_vercel_help_chat(request)

        self.assertEqual(request.status, 200)
        response = json.loads(request.wfile.getvalue().decode("utf-8"))
        self.assertEqual(response["status"], "success")
        self.assertEqual(client.context["recommendation_context"]["selected_place"]["name"], "제주문학관")


class FakeVercelRequest:
    def __init__(self, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = BytesIO(raw)
        self.wfile = BytesIO()
        self.status = None
        self.response_headers = []

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        pass


if __name__ == "__main__":
    unittest.main()
