import copy
import json
import unittest

from src.rag_query import MAX_QUERY_TEXT_LENGTH, TRAVELER_SUMMARY_KEYS, parse_query_intent


class RagQueryTests(unittest.TestCase):
    def test_extracts_jeju_place_accessibility_preferences_and_avoidance(self):
        result = parse_query_intent(
            "  제주시에서\x00 휠체어로 갈 수 있는 실내 문화시설을 찾아줘. "
            "계단과 혼잡은 피하고 장애인 화장실과 주차장이 필요해.  "
        )

        self.assertEqual(result["intent"], "place_search")
        self.assertEqual(result["regions"], ["제주시"])
        self.assertIn("indoor", result["categories"])
        self.assertIn("culture", result["categories"])
        self.assertIn("wheelchair_user", result["traveler_summary"]["traveler_type"])
        self.assertIn("휠체어 접근", result["traveler_summary"]["required_accessibility"])
        self.assertIn("장애인 화장실", result["traveler_summary"]["required_accessibility"])
        self.assertIn("주차", result["traveler_summary"]["required_accessibility"])
        self.assertIn("실내", result["traveler_summary"]["preferred_themes"])
        self.assertIn("계단", result["traveler_summary"]["avoid"])
        self.assertIn("혼잡", result["traveler_summary"]["avoid"])
        self.assertNotIn("\x00", result["query_text"])
        self.assertEqual(result["query_text"], result["query_text"].strip())

    def test_extracts_support_resource_emergency_and_charging_signals(self):
        result = parse_query_intent(
            "서귀포시 근처 대형병원과 약국, 전동휠체어 급속충전기, "
            "교통약자 이동지원센터를 찾아줘. 응급 상황이야."
        )

        self.assertEqual(result["intent"], "emergency_support")
        self.assertEqual(result["regions"], ["서귀포시"])
        self.assertIn("medical_support", result["categories"])
        self.assertIn("transport", result["categories"])
        self.assertEqual(
            set(result["resource_types"]),
            {"hospital", "pharmacy", "power_wheelchair_fast_charger", "mobility_support_center"},
        )
        self.assertTrue(result["signals"]["emergency"])
        self.assertTrue(result["signals"]["charging"])
        self.assertIn("전동휠체어 충전", result["traveler_summary"]["required_accessibility"])

    def test_extracts_tourism_welfare_and_call_taxi_phrases(self):
        result = parse_query_intent("제주도 관광 약자 콜택시와 관광 관련 복지 서비스를 알려줘")

        self.assertEqual(result["intent"], "support_resource_search")
        self.assertEqual(result["regions"], ["제주특별자치도"])
        self.assertEqual(
            result["resource_types"],
            ["mobility_support_center", "tourism_welfare_service"],
        )
        self.assertFalse(result["signals"]["emergency"])

    def test_merges_traveler_summary_without_mutating_input(self):
        traveler_summary = {
            "traveler_type": ["senior"],
            "mobility_conditions": "휴식 필요",
            "preferred_themes": ["문화", "문화"],
            "required_accessibility": ["주차"],
            "avoid": ["강풍"],
            "private_diagnosis": ["반환하면 안 됨"],
        }
        original = copy.deepcopy(traveler_summary)

        result = parse_query_intent(
            "유모차를 이용하고 오래 걷기 힘들어서 공원과 휴식 공간이 필요해",
            traveler_summary,
        )

        self.assertEqual(traveler_summary, original)
        self.assertEqual(result["traveler_summary"]["traveler_type"][0], "senior")
        self.assertIn("stroller_family", result["traveler_summary"]["traveler_type"])
        self.assertIn("휴식 필요", result["traveler_summary"]["mobility_conditions"])
        self.assertIn("긴 걷기 어려움", result["traveler_summary"]["mobility_conditions"])
        self.assertEqual(result["traveler_summary"]["preferred_themes"].count("문화"), 1)
        self.assertNotIn("private_diagnosis", result["traveler_summary"])

    def test_avoided_theme_is_not_returned_as_a_preference_or_category(self):
        result = parse_query_intent("바다는 피하고 조용한 실내와 숲을 선호해")

        self.assertNotIn("sea", result["categories"])
        self.assertIn("indoor", result["categories"])
        self.assertIn("forest", result["categories"])
        self.assertNotIn("바다", result["traveler_summary"]["preferred_themes"])
        self.assertIn("바다", result["traveler_summary"]["avoid"])
        self.assertIn("실내", result["traveler_summary"]["preferred_themes"])
        self.assertIn("숲", result["traveler_summary"]["preferred_themes"])

    def test_common_avoid_wording_is_normalized(self):
        result = parse_query_intent("계단 회피, 비포장 길은 제외하고 싶어")

        self.assertIn("계단", result["traveler_summary"]["avoid"])
        self.assertIn("비포장", result["traveler_summary"]["avoid"])
        self.assertIn("계단 회피", result["traveler_summary"]["mobility_conditions"])

    def test_empty_query_can_still_use_explicit_structured_profile(self):
        result = parse_query_intent("", {"traveler_type": ["wheelchair_user"]})

        self.assertEqual(result["intent"], "place_search")
        self.assertEqual(result["query_text"], "")
        self.assertEqual(result["traveler_summary"]["traveler_type"], ["wheelchair_user"])
        self.assertEqual(result["regions"], [])

    def test_empty_and_non_string_queries_return_conservative_json_safe_contract(self):
        for query in (None, " \t\n\x00 ", {"query": "제주"}):
            with self.subTest(query=query):
                result = parse_query_intent(query)

                self.assertEqual(result["intent"], "unknown")
                self.assertEqual(result["query_text"], "")
                self.assertEqual(result["regions"], [])
                self.assertEqual(result["categories"], [])
                self.assertEqual(result["resource_types"], [])
                self.assertTrue({"emergency", "charging"}.issubset(result["signals"]))
                self.assertFalse(any(result["signals"].values()))
                self.assertEqual(set(result["traveler_summary"]), set(TRAVELER_SUMMARY_KEYS))
                self.assertFalse(any(result["traveler_summary"].values()))
                json.dumps(result, ensure_ascii=False)

    def test_query_text_is_bounded_and_has_no_separate_health_detail_fields(self):
        query = "제주시에서 휠체어 여행지를 찾아줘 " + ("가" * (MAX_QUERY_TEXT_LENGTH + 100))
        result = parse_query_intent(query, {"unknown_health_field": ["민감 정보"]})

        self.assertEqual(len(result["query_text"]), MAX_QUERY_TEXT_LENGTH)
        self.assertEqual(
            set(result),
            {
                "intent",
                "query_text",
                "regions",
                "categories",
                "excluded_categories",
                "resource_types",
                "traveler_summary",
                "signals",
            },
        )
        self.assertNotIn("unknown_health_field", result["traveler_summary"])
        json.dumps(result, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
