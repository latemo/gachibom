import http.client
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from src.recommendation_api import MAX_REQUEST_BODY_BYTES, create_server


ROOT = Path(__file__).resolve().parents[1]


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

        schema = json.loads((ROOT / "data" / "schemas" / "recommendation_result.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(payload["recommendation"])), [])

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
            def generate_reply(self, context, *, model):
                return {
                    "answer": f"{context['question']} 답변",
                    "followups": ["방문 전 확인은?"],
                    "handoff_checklist": ["공식 정보 확인"],
                }

        with patch("src.recommendation_api.openai_help_chatbot_client_from_env", return_value=FakeHelpClient()):
            status, payload = self.post_json("/api/help-chat", {"question": "점수는 어떻게 읽나요?"})

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["model"], "gpt-5-mini")
        self.assertIn("점수는 어떻게 읽나요?", payload["answer"])

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


if __name__ == "__main__":
    unittest.main()
