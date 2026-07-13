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
        self.assertEqual(len(seed["saved_route_places"]), len(load_places()))
        self.assertEqual(
            {item["spot_id"] for item in seed["saved_route_places"]},
            {place["id"] for place in load_places()},
        )
        self.assertTrue(all(item["duration_minutes"] for item in seed["saved_route_places"]))
        self.assertTrue(all(item["info_url"].startswith(("https://", "http://")) for item in seed["saved_route_places"]))
        self.assertEqual(
            sum(item["available"] for item in seed["saved_route_places"]),
            seed["public_gate"]["app_candidate_places"],
        )
        self.assertTrue(all(item["visit_info"]["verification_status"] == "needs_check" for item in seed["saved_route_places"]))
        self.assertTrue(all(item["visit_info"]["address"] is None for item in seed["saved_route_places"]))
        self.assertEqual(
            sum(item["location"] is not None for item in seed["saved_route_places"]),
            len(load_location_index()),
        )
        self.assertTrue(
            all(item["location"]["point_role"] for item in seed["saved_route_places"] if item["location"])
        )
        for scenario in seed["scenarios"]:
            self.assertGreater(len(scenario["places"]), 0)
            self.assertFalse(any(place["blocked"] for place in scenario["places"]))
            self.assertFalse(any(place["location"] is None for place in scenario["places"]))
        self.assertTrue(
            any(
                place["location"]["point_role"] != "poi"
                for scenario in seed["scenarios"]
                for place in scenario["places"]
            )
        )

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
            visit_rows = [item["visit_info"] for item in seed["saved_route_places"]]
            self.assertEqual(sum(bool(info["address"]) for info in visit_rows), 50)
            self.assertEqual(sum(bool(info["phone"]) for info in visit_rows), 32)
            self.assertEqual(sum(bool(info["operating_hours"]) for info in visit_rows), 15)
            self.assertEqual(sum(bool(info["official_url"]) for info in visit_rows), 37)
            self.assertEqual(sum(bool(info["reservation_url"]) for info in visit_rows), 2)
            self.assertEqual(sum(bool(info["evidence"]) for info in visit_rows), 51)
            self.assertEqual(sum(bool(info["last_verified_at"]) for info in visit_rows), 37)
            self.assertEqual(sum(bool(info["source_updated_at"]) for info in visit_rows), 31)
            self.assertEqual(sum(info["service_status"] == "active" for info in visit_rows), 14)
            self.assertEqual(
                sum(item["location"] is not None for item in seed["saved_route_places"]),
                90,
            )
            location_roles = {
                item["spot_id"]: item["location"]["point_role"]
                for item in seed["saved_route_places"]
                if item["location"]
            }
            self.assertEqual(location_roles["jeju_tourism_weak_040"], "route_end_reference")
            self.assertEqual(location_roles["jeju_tourism_weak_047"], "viewpoint")
            hidden_place = next(
                item
                for item in seed["saved_route_places"]
                if item["spot_id"] == "jeju_indoor_sumokwon_theme_028"
            )
            self.assertFalse(hidden_place["available"])
            self.assertFalse(
                any(
                    place["spot_id"] == hidden_place["spot_id"]
                    for scenario in seed["scenarios"]
                    for place in scenario["places"]
                )
            )
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

    def test_committed_seed_contains_reconstructible_score_traces(self):
        seed = json.loads((ROOT / "web" / "data" / "app_recommendation_seed.json").read_text(encoding="utf-8"))

        for scenario in seed["scenarios"]:
            places = scenario["places"]
            for place in places:
                trace = place["score"]["calculation_trace"]
                reconstructed = trace["base_total"]
                reconstructed += sum(item["delta"] for item in trace["bonuses"])
                reconstructed += sum(item["delta"] for item in trace["deductions"])
                for cap in trace["caps"]:
                    self.assertEqual(cap["before"], reconstructed)
                    reconstructed = cap["after"]
                self.assertEqual(reconstructed, trace["final_total"])
                self.assertEqual(trace["final_total"], place["score"]["total"])

            for component, item in scenario["recommendation"]["score"]["breakdown"].items():
                expected = int(round(sum(place["score"]["breakdown"][component]["score"] for place in places) / len(places)))
                self.assertEqual(item["score"], expected)


if __name__ == "__main__":
    unittest.main()
