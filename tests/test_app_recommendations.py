import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.app_recommendations import build_app_recommendation_seed
from src.place_locations import build_place_location_index


ROOT = Path(__file__).resolve().parents[1]


def load_places():
    return json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))


def load_location_index():
    return build_place_location_index(
        load_places(),
        roadview_metadata=json.loads((ROOT / "data" / "roadview_image_metadata.json").read_text(encoding="utf-8")),
        overrides=json.loads((ROOT / "data" / "place_location_overrides.json").read_text(encoding="utf-8"))["items"],
    )


class AppRecommendationSeedTests(unittest.TestCase):
    def test_build_app_recommendation_seed_matches_schema(self):
        seed = build_app_recommendation_seed(
            load_places(),
            generated_at=date(2026, 7, 8),
            location_index=load_location_index(),
        )
        schema = json.loads((ROOT / "data" / "schemas" / "app_recommendation_seed.schema.json").read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(seed))
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(seed["scenarios"]), 5)
        self.assertEqual(len(seed["official_courses"]), 0)
        self.assertGreater(seed["public_gate"]["app_candidate_places"], 0)
        for scenario in seed["scenarios"]:
            self.assertGreater(len(scenario["places"]), 0)
            self.assertFalse(any(place["blocked"] for place in scenario["places"]))
            self.assertFalse(any(place["location"] is None for place in scenario["places"]))

    def test_build_app_recommendation_seed_cli_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "app_recommendation_seed.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_app_recommendation_seed.py"),
                    "--places",
                    str(ROOT / "data" / "jeju_accessible_spots.json"),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("scenarios:", result.stdout)
            seed = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(seed["generated_at"], "2026-07-08")
            self.assertEqual(len(seed["official_courses"]), 16)
            self.assertTrue(
                any(stop["promoted_candidate"] for course in seed["official_courses"] for stop in course["stops"])
            )

    def test_seed_scenarios_are_condition_specific(self):
        seed = build_app_recommendation_seed(
            load_places(),
            generated_at=date(2026, 7, 8),
            location_index=load_location_index(),
        )
        scenarios = {scenario["id"]: scenario for scenario in seed["scenarios"]}

        route_signatures = {
            scenario_id: tuple(place["spot_id"] for place in scenario["places"])
            for scenario_id, scenario in scenarios.items()
        }
        self.assertGreaterEqual(len(set(route_signatures.values())), 4)

        diet_categories = {place["category"] for place in scenarios["diet_restricted"]["places"]}
        self.assertTrue(diet_categories.isdisjoint({"restaurant", "food_market"}))

        weather_places = scenarios["weather_sensitive"]["places"]
        self.assertFalse(any(place["category"] == "sea" for place in weather_places))
        self.assertFalse(any(place["effort"]["weather_sensitivity"] == "high" for place in weather_places))

        wheelchair_route = route_signatures["wheelchair_access"]
        stroller_route = route_signatures["stroller_family"]
        self.assertNotEqual(wheelchair_route, stroller_route)
        self.assertTrue(
            any(place["category"] in {"forest", "rest_area"} for place in scenarios["stroller_family"]["places"])
        )


if __name__ == "__main__":
    unittest.main()
