import json
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.scoring import build_recommendation_result, grade_for_score, rank_places, score_place


ROOT = Path(__file__).resolve().parents[1]


def load_places():
    return json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))


def place_by_id(spot_id):
    for place in load_places():
        if place["id"] == spot_id:
            return place
    raise AssertionError(f"missing place {spot_id}")


class ScoringTests(unittest.TestCase):
    def test_place_cards_match_schema(self):
        schema = json.loads(
            (ROOT / "data" / "schemas" / "accessibility_place_card.schema.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        for place in load_places():
            errors = list(validator.iter_errors(place))
            self.assertEqual(errors, [], place["id"])

    def test_grade_boundaries(self):
        self.assertEqual(grade_for_score(90), "A")
        self.assertEqual(grade_for_score(70), "B")
        self.assertEqual(grade_for_score(50), "C")
        self.assertEqual(grade_for_score(30), "D")
        self.assertEqual(grade_for_score(29), "F")

    def test_verified_indoor_place_scores_well_for_wheelchair_user(self):
        traveler = {
            "traveler_type": ["wheelchair_user"],
            "mobility_conditions": ["긴 걷기 어려움"],
            "preferred_themes": ["실내", "문화"],
            "required_accessibility": ["장애인 화장실", "주차", "휠체어 접근"],
            "avoid": ["긴 야외 체류"],
        }
        score = score_place(
            place_by_id("jeju_indoor_literature_022"),
            traveler,
            today=date(2026, 7, 7),
        )
        self.assertGreaterEqual(score.total, 70)
        self.assertIn(score.grade, {"A", "B"})
        self.assertFalse(score.blocked)
        self.assertEqual(score.confidence, "high")

    def test_needs_check_place_is_capped_and_low_confidence(self):
        traveler = {
            "traveler_type": ["wheelchair_user"],
            "mobility_conditions": ["긴 걷기 어려움"],
            "preferred_themes": ["바다"],
            "required_accessibility": ["장애인 화장실", "주차"],
            "avoid": [],
        }
        score = score_place(
            place_by_id("jeju_sea_songaksan_023"),
            traveler,
            today=date(2026, 7, 7),
        )
        self.assertLessEqual(score.total, 84)
        self.assertNotEqual(score.grade, "A")
        self.assertEqual(score.confidence, "low")
        self.assertGreater(len(score.deduction_reasons), 0)

    def test_calculation_trace_reconstructs_final_place_score(self):
        traveler = {
            "traveler_type": ["recovery_traveler", "diet_restricted_traveler"],
            "mobility_conditions": ["체력 저하"],
            "preferred_themes": ["실내", "휴식"],
            "required_accessibility": ["장애인 화장실", "주차"],
            "avoid": ["식당 제외", "외부 음식 제한"],
        }
        score = score_place(
            place_by_id("jeju_other_dongmun_market_029"),
            traveler,
            today=date(2026, 7, 7),
        )
        trace = score.to_dict()["score"]["calculation_trace"]

        self.assertEqual(
            trace["base_total"],
            sum(item["score"] for item in score.breakdown.values()),
        )
        reconstructed = trace["base_total"]
        reconstructed += sum(item["delta"] for item in trace["bonuses"])
        reconstructed += sum(item["delta"] for item in trace["deductions"])
        for cap in trace["caps"]:
            self.assertEqual(cap["before"], reconstructed)
            reconstructed = cap["after"]

        self.assertEqual(reconstructed, trace["final_total"])
        self.assertEqual(trace["final_total"], score.total)
        self.assertTrue(all(item["delta"] < 0 for item in trace["deductions"]))
        self.assertTrue(any(cap["id"] == "blocked" for cap in trace["caps"]))

    def test_high_walking_course_is_penalized_for_recovery_traveler(self):
        traveler = {
            "traveler_type": ["recovery_traveler"],
            "mobility_conditions": ["체력 저하", "긴 걷기 어려움"],
            "preferred_themes": ["바다"],
            "required_accessibility": ["휴식 공간"],
            "avoid": ["장시간 야외 체류"],
        }
        score = score_place(
            place_by_id("jeju_sea_olle17_019"),
            traveler,
            today=date(2026, 7, 7),
        )
        self.assertLess(score.total, 70)
        self.assertTrue(any("높은 도보 부담" in reason or "긴 걷기" in reason for reason in score.deduction_reasons))

    def test_recommendation_result_matches_schema(self):
        traveler = {
            "traveler_type": ["senior"],
            "mobility_conditions": ["긴 걷기 어려움", "휴식 필요"],
            "preferred_themes": ["실내", "문화"],
            "required_accessibility": ["장애인 화장실", "주차"],
            "avoid": ["장시간 야외 체류"],
        }
        scores = rank_places(load_places(), traveler, limit=3, today=date(2026, 7, 7))
        result = build_recommendation_result(
            scores,
            traveler,
            safety_notice="이 서비스는 의료 판단이나 여행 가능성을 보장하지 않습니다.",
        )
        schema = json.loads(
            (ROOT / "data" / "schemas" / "recommendation_result.schema.json").read_text(encoding="utf-8")
        )
        errors = list(Draft202012Validator(schema).iter_errors(result))
        self.assertEqual(errors, [])

    def test_course_breakdown_averages_selected_place_components(self):
        traveler = {
            "traveler_type": ["wheelchair_user"],
            "mobility_conditions": ["긴 걷기 어려움"],
            "preferred_themes": ["바다"],
            "required_accessibility": ["장애인 화장실", "주차"],
            "avoid": [],
        }
        scores = [
            score_place(place_by_id(spot_id), traveler, today=date(2026, 7, 7))
            for spot_id in (
                "jeju_indoor_literature_022",
                "jeju_sea_songaksan_023",
                "jeju_sea_olle17_019",
                "jeju_other_dongmun_market_029",
            )
        ]
        result = build_recommendation_result(
            scores,
            traveler,
            safety_notice="이 서비스는 의료 판단이나 여행 가능성을 보장하지 않습니다.",
        )

        for component, item in result["score"]["breakdown"].items():
            expected = int(
                round(
                    sum(score.breakdown[component]["score"] for score in scores)
                    / len(scores)
                )
            )
            self.assertEqual(item["score"], expected)
            self.assertIn("4곳", item["reason"])

        self.assertTrue(
            any(
                result["score"]["breakdown"][component]["score"]
                != scores[0].breakdown[component]["score"]
                for component in result["score"]["breakdown"]
            )
        )

    def test_food_restriction_blocks_food_market_and_penalizes_cafe(self):
        traveler = {
            "traveler_type": ["recovery_traveler", "diet_restricted_traveler"],
            "mobility_conditions": ["체력 저하"],
            "preferred_themes": ["실내", "휴식"],
            "required_accessibility": ["장애인 화장실", "주차"],
            "avoid": ["식당 제외", "외부 음식 제한"],
        }
        market_score = score_place(
            place_by_id("jeju_other_dongmun_market_029"),
            traveler,
            today=date(2026, 7, 7),
        )
        self.assertTrue(market_score.blocked)
        self.assertLessEqual(market_score.total, 49)

        cafe = place_by_id("jeju_cafe_osulloc_013")
        restricted_score = score_place(cafe, traveler, today=date(2026, 7, 7))
        unrestricted_score = score_place(
            cafe,
            {
                "traveler_type": ["recovery_traveler"],
                "mobility_conditions": ["체력 저하"],
                "preferred_themes": ["실내", "휴식"],
                "required_accessibility": ["장애인 화장실", "주차"],
                "avoid": [],
            },
            today=date(2026, 7, 7),
        )
        self.assertLess(restricted_score.total, unrestricted_score.total)
        self.assertTrue(any("음식 제한" in reason for reason in restricted_score.deduction_reasons))

    def test_tourism_weak_course_reference_adds_fit_reason_bonus(self):
        traveler = {
            "traveler_type": ["wheelchair_user"],
            "mobility_conditions": ["긴 걷기 어려움"],
            "preferred_themes": ["문화"],
            "required_accessibility": ["장애인 화장실"],
            "avoid": [],
        }
        base_place = place_by_id("jeju_indoor_literature_022")
        referenced_place = deepcopy(base_place)
        referenced_place["tourism_weak_course_references"] = [
            {
                "course_id": "tourism_weak_course_test",
                "course_title": "테스트 추천코스",
                "recommendation_by_type": {"wheelchair_user": "적극추천"},
            }
        ]

        base_score = score_place(base_place, traveler, today=date(2026, 7, 7))
        referenced_score = score_place(referenced_place, traveler, today=date(2026, 7, 7))

        self.assertGreater(referenced_score.total, base_score.total)
        self.assertTrue(any("제주관광공사 관광약자 추천코스" in reason for reason in referenced_score.fit_reasons))
        tourism_bonus = next(
            item
            for item in referenced_score.calculation_trace["bonuses"]
            if item["id"] == "tourism_weak_course"
        )
        self.assertEqual(tourism_bonus["delta"], 6)

    def test_sensory_sensitive_user_gets_media_art_penalty(self):
        traveler = {
            "traveler_type": ["sensory_sensitive_traveler"],
            "mobility_conditions": ["어두운 곳과 강한 조명이 힘듦"],
            "preferred_themes": ["실내"],
            "required_accessibility": ["장애인 화장실"],
            "avoid": ["강한 조명"],
        }
        score = score_place(
            place_by_id("jeju_indoor_bunker_lumieres_010"),
            traveler,
            today=date(2026, 7, 7),
        )
        self.assertTrue(any("감각 민감" in reason for reason in score.deduction_reasons))
        self.assertIn("조명과 소리 자극", score.check_before_visit)

    def test_empty_recommendation_result_matches_schema(self):
        traveler = {
            "traveler_type": ["wheelchair_user"],
            "mobility_conditions": ["긴 걷기 어려움"],
            "preferred_themes": ["바다"],
            "required_accessibility": ["장애인 화장실"],
            "avoid": [],
        }
        result = build_recommendation_result(
            [],
            traveler,
            safety_notice="이 서비스는 의료 판단이나 여행 가능성을 보장하지 않습니다.",
        )
        schema = json.loads(
            (ROOT / "data" / "schemas" / "recommendation_result.schema.json").read_text(encoding="utf-8")
        )
        errors = list(Draft202012Validator(schema).iter_errors(result))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
