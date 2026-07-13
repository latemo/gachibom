import copy
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


class GroundedFakeExplanationClient:
    def __init__(self):
        self.context = None

    def generate_summary(self, context, *, model):
        self.context = context
        evidence_id = context["retrieval"]["evidence"][0]["evidence_id"]
        return {
            "headline": "공식 근거를 확인한 추천",
            "rationale": ["검색 조건과 접근성 근거가 연결됩니다."],
            "cautions": ["방문 전 최신 운영 정보를 확인하세요."],
            "next_checks": ["공식 출처 확인"],
            "evidence_ids": [evidence_id, "ev_model_invented"],
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

    def test_blank_query_preserves_existing_recommendation_path(self):
        profile = {
            "traveler_type": ["wheelchair_user"],
            "mobility_conditions": ["짧은 이동"],
            "preferred_themes": ["실내", "문화"],
            "required_accessibility": ["장애인 화장실"],
            "avoid": ["계단"],
        }
        baseline = build_runtime_recommendation(
            load_places(), profile, today=date(2026, 7, 8), use_ai=False
        )
        blank_query = build_runtime_recommendation(
            load_places(), profile, today=date(2026, 7, 8), query="   ", use_ai=False
        )

        self.assertEqual(blank_query["traveler_summary"], baseline["traveler_summary"])
        self.assertEqual(blank_query["recommendation"], baseline["recommendation"])
        self.assertEqual(blank_query["places"], baseline["places"])
        self.assertEqual(blank_query["retrieval"]["status"], "not_requested")
        self.assertEqual(blank_query["engine"]["retrieval"], "not_requested")

    def test_natural_language_query_retrieves_then_scores_grounded_places(self):
        result = build_runtime_recommendation(
            load_places(),
            {},
            today=date(2026, 7, 8),
            query="제주시에서 휠체어로 이용할 실내 문학관과 장애인 화장실",
            use_ai=False,
        )

        self.assertEqual(result["retrieval"]["status"], "applied")
        self.assertEqual(result["retrieval"]["query_intent"]["regions"], ["제주시"])
        self.assertNotIn("query_text", result["retrieval"]["query_intent"])
        self.assertTrue(result["places"])
        self.assertIn("제주문학관", [place["name"] for place in result["places"]])
        self.assertEqual(
            [place["spot_id"] for place in result["places"]],
            [match["spot_id"] for match in result["retrieval"]["matches"]],
        )
        sources = result["retrieval"]["matches"][0]["evidence_bundle"]["sources"]
        self.assertTrue(sources)
        self.assertRegex(sources[0]["evidence_id"], r"^ev_[0-9a-f]{16}$")
        self.assertEqual(
            result["retrieval"]["matches"][0]["evidence_bundle"]["verification"]["freshness"],
            "recent",
        )

    def test_support_resource_query_fails_closed_until_corpus_is_available(self):
        result = build_runtime_recommendation(
            load_places(),
            {},
            today=date(2026, 7, 8),
            query="전동휠체어 급속충전기와 교통약자 이동지원센터를 찾아줘",
            use_ai=False,
        )

        self.assertEqual(result["retrieval"]["status"], "resource_data_gap")
        self.assertIn("power_wheelchair_fast_charger", result["retrieval"]["data_gaps"])
        self.assertIn("mobility_support_center", result["retrieval"]["data_gaps"])
        self.assertEqual(result["places"], [])
        self.assertEqual(result["recommendation"]["recommended_spots"], [])
        self.assertEqual(result["recommendation"]["course"]["route"], [])

    def test_unmatched_rag_query_returns_no_match_without_placeholder_route(self):
        result = build_runtime_recommendation(
            load_places(),
            {},
            today=date(2026, 7, 8),
            query="존재하지않는검색어abcxyz",
            use_ai=False,
        )

        self.assertEqual(result["retrieval"]["status"], "no_match")
        self.assertEqual(result["places"], [])
        self.assertEqual(result["recommendation"]["course"]["route"], [])

    def test_ai_citations_are_resolved_from_server_evidence_only(self):
        client = GroundedFakeExplanationClient()
        result = build_runtime_recommendation(
            load_places(),
            {},
            today=date(2026, 7, 8),
            query="제주시 휠체어 실내 문학관",
            explanation_client=client,
        )

        self.assertTrue(client.context["retrieval"]["evidence"])
        self.assertEqual(len(result["ai_summary"]["citations"]), 1)
        citation = result["ai_summary"]["citations"][0]
        self.assertRegex(citation["evidence_id"], r"^ev_[0-9a-f]{16}$")
        self.assertTrue(citation["source_url"].startswith(("https://", "http://")))
        self.assertNotIn("ev_model_invented", json.dumps(result["ai_summary"], ensure_ascii=False))

    def test_build_runtime_recommendation_excludes_closed_services_without_mutating_input(
        self,
    ):
        places = copy.deepcopy(load_places()[:4])
        statuses = ("permanently_closed", "temporarily_closed", "unknown", "active")
        for place, status in zip(places, statuses):
            place["visit_info"] = {"service_status": status}
        original_places = copy.deepcopy(places)

        result = build_runtime_recommendation(
            places,
            {},
            today=date(2026, 7, 13),
            limit=4,
            use_ai=False,
        )

        self.assertEqual(
            {place["spot_id"] for place in result["places"]},
            {places[2]["id"], places[3]["id"]},
        )
        self.assertEqual(places, original_places)

    def test_build_runtime_recommendation_handles_no_candidates_after_service_status_gate(
        self,
    ):
        places = copy.deepcopy(load_places()[:2])
        places[0]["visit_info"] = {"service_status": "permanently_closed"}
        places[1]["visit_info"] = {"service_status": "temporarily_closed"}

        result = build_runtime_recommendation(
            places,
            {},
            today=date(2026, 7, 13),
            limit=4,
            use_ai=False,
        )

        self.assertEqual(result["places"], [])
        self.assertEqual(result["recommendation"]["recommended_spots"], [])
        self.assertEqual(
            result["recommendation"]["course"]["route"][0]["spot_id"],
            "no_recommendation",
        )

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
