import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.recommendation_service import (
    DEFAULT_OPENAI_MODEL,
    OpenAIResponsesExplanationClient,
    build_runtime_recommendation,
    extract_response_text,
    normalize_ai_summary,
    normalize_traveler_summary,
    openai_client_from_env,
    parse_json_object,
)


ROOT = Path(__file__).resolve().parents[1]


def load_places():
    return json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))


class FakeExplanationClient:
    def generate_summary(self, context, *, model):
        return {
            "headline": f"{model} 기반 설명",
            "rationale": [context["places"][0]["name"], context["places"][0]["name"]],
            "cautions": ["방문 전 운영 상태 확인"],
            "next_checks": ["화장실 운영 여부 확인"],
        }


class RecommendationServiceTests(unittest.TestCase):
    def test_normalize_traveler_summary_keeps_known_keys_only(self):
        summary = normalize_traveler_summary(
            {
                "traveler_type": "wheelchair_user",
                "mobility_conditions": ["긴 걷기 어려움", "긴 걷기 어려움"],
                "ignored": ["x"],
            }
        )
        self.assertEqual(summary["traveler_type"], ["wheelchair_user"])
        self.assertEqual(summary["mobility_conditions"], ["긴 걷기 어려움"])
        self.assertEqual(summary["avoid"], [])
        self.assertNotIn("ignored", summary)

    def test_build_runtime_recommendation_without_api_key_uses_local_scoring(self):
        result = build_runtime_recommendation(
            load_places(),
            {
                "traveler_type": ["diet_restricted_traveler"],
                "mobility_conditions": ["체력 저하"],
                "preferred_themes": ["실내"],
                "required_accessibility": ["장애인 화장실", "주차"],
                "avoid": ["식당 제외", "외부 음식 제한"],
            },
            today=date(2026, 7, 8),
            use_ai=True,
            explanation_client=None,
        )
        self.assertEqual(result["engine"]["ai_status"], "disabled_no_key")
        self.assertGreater(len(result["places"]), 0)
        self.assertFalse(any(place["blocked"] for place in result["places"]))
        self.assertNotIn("동문재래시장", result["recommendation"]["recommended_spots"])

    def test_build_runtime_recommendation_stroller_family_includes_restful_place(self):
        result = build_runtime_recommendation(
            load_places(),
            {
                "traveler_type": ["stroller_family"],
                "mobility_conditions": ["계단 회피", "짧은 이동", "휴식 필요"],
                "preferred_themes": ["실내", "공원", "문화"],
                "required_accessibility": ["화장실", "주차", "휴식 공간"],
                "avoid": ["좁은 길", "비포장"],
            },
            today=date(2026, 7, 8),
            use_ai=False,
        )
        categories = {place["category"] for place in result["places"]}
        self.assertTrue(categories & {"forest", "rest_area"})
        self.assertIn("사려니숲길 무장애나눔길", result["recommendation"]["recommended_spots"])

    def test_build_runtime_recommendation_with_fake_ai_summary(self):
        result = build_runtime_recommendation(
            load_places(),
            {
                "traveler_type": ["recovery_traveler"],
                "mobility_conditions": ["긴 걷기 어려움"],
                "preferred_themes": ["실내", "문화"],
                "required_accessibility": ["장애인 화장실"],
                "avoid": [],
            },
            today=date(2026, 7, 8),
            explanation_client=FakeExplanationClient(),
        )
        self.assertEqual(result["engine"]["ai_status"], "success")
        self.assertEqual(result["ai_summary"]["model"], DEFAULT_OPENAI_MODEL)
        self.assertEqual(len(result["ai_summary"]["rationale"]), 1)

    def test_normalize_ai_summary_limits_overlong_generated_text(self):
        long_repeated = "제주한란전시관 방문 전 확인 " * 20
        summary = normalize_ai_summary(
            {
                "headline": "회복 여행자에게 맞춘 조용한 실내 중심 추천입니다. " * 4,
                "rationale": [long_repeated, long_repeated],
                "cautions": ["운영 여부 확인"],
                "next_checks": [long_repeated],
            },
            DEFAULT_OPENAI_MODEL,
        )
        self.assertLessEqual(len(summary["headline"]), 80)
        self.assertEqual(len(summary["rationale"]), 1)
        self.assertLessEqual(len(summary["rationale"][0]), 123)
        self.assertLessEqual(len(summary["next_checks"][0]), 123)

    def test_openai_client_from_env_does_not_exist_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(openai_client_from_env())

    def test_parse_responses_api_text_outputs(self):
        body = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"headline":"요약","rationale":["근거"],"cautions":[],"next_checks":[]}',
                        }
                    ]
                }
            ]
        }
        parsed = parse_json_object(extract_response_text(body))
        self.assertEqual(parsed["headline"], "요약")

    def test_openai_client_keeps_authorization_header_out_of_errors(self):
        client = OpenAIResponsesExplanationClient("secret-test-key")
        with patch("urllib.request.urlopen", side_effect=RuntimeError("network down")):
            with self.assertRaises(RuntimeError) as context:
                client.generate_summary({"places": []}, model="gpt-5-mini")
        self.assertNotIn("secret-test-key", str(context.exception))


if __name__ == "__main__":
    unittest.main()
