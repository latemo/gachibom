import json
import unittest
from pathlib import Path

from src.tourism_weak_courses import (
    SOURCE_URL,
    augment_places_with_tourism_weak_courses,
    build_promoted_course_place_cards,
    build_tourism_weak_course_dataset,
    read_course_csv,
)


ROOT = Path(__file__).resolve().parents[1]


def load_places():
    return json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))


class TourismWeakCoursesTests(unittest.TestCase):
    def test_imported_course_dataset_matches_existing_place_cards(self):
        rows = read_course_csv(ROOT / "data" / "raw" / "jeju_tourism_weak_recommendation_courses_20260528.csv")
        dataset = build_tourism_weak_course_dataset(rows, load_places())

        self.assertEqual(dataset["summary"]["courses"], 16)
        self.assertEqual(dataset["summary"]["stops"], 62)
        self.assertEqual(dataset["summary"]["matched_stops"], 62)
        self.assertEqual(dataset["summary"]["unmatched_places"], 0)
        self.assertIn("jeju_forest_cheonjiyeon_014", dataset["place_references"])
        self.assertIn("jeju_sea_saeyeongyo_039", dataset["place_references"])
        self.assertIn("jeju_other_dongmun_market_029", dataset["place_references"])
        self.assertTrue(
            any(
                reference["source_place_name"] == "돌문화공원"
                for reference in dataset["place_references"]["jeju_tourism_weak_011"]
            )
        )

    def test_augment_places_adds_references_and_public_source_without_mutating_input(self):
        rows = read_course_csv(ROOT / "data" / "raw" / "jeju_tourism_weak_recommendation_courses_20260528.csv")
        places = load_places()
        dataset = build_tourism_weak_course_dataset(rows, places)
        augmented = augment_places_with_tourism_weak_courses(places, dataset)

        original = next(place for place in places if place["id"] == "jeju_forest_cheonjiyeon_014")
        changed = next(place for place in augmented if place["id"] == "jeju_forest_cheonjiyeon_014")

        self.assertNotIn("tourism_weak_course_references", original)
        self.assertIn("tourism_weak_course_references", changed)
        self.assertTrue(any(source["url"] == SOURCE_URL for source in changed["sources"]))

    def test_promoted_course_place_cards_are_conservative_schema_like_cards(self):
        dataset = {
            "courses": [
                {
                    "id": "tourism_weak_course_test",
                    "title": "테스트 코스",
                    "total_travel_minutes": 120,
                    "recommendation_by_type": {
                        "wheelchair_user": "조건부권장",
                        "senior_or_pregnant": "추천",
                        "stroller_family": "추천",
                    },
                    "stops": [
                        {
                            "order": 1,
                            "name": "테스트 해변",
                            "description": "정돈된 산책로가 있으나 일부 경사 구간 확인 필요",
                            "cautions": "장애인 화장실과 주차는 있으나 경사로 주의 필요",
                            "hashtags": ["해변"],
                            "mandatory_facilities": ["주 출입구 접근로", "장애인 전용 주차구역", "장애인 화장실"],
                            "matched_spot_id": "",
                        }
                    ],
                }
            ]
        }

        cards = build_promoted_course_place_cards(dataset, [], checked_at="2026-05-28")

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["name"], "테스트 해변")
        self.assertEqual(cards[0]["category"], "sea")
        self.assertEqual(cards[0]["verification"]["status"], "partial")
        self.assertEqual(cards[0]["accessibility"]["parking"]["state"], "yes")
        self.assertIn("rental_or_assistance", cards[0]["verification"]["missing_fields"])


if __name__ == "__main__":
    unittest.main()
