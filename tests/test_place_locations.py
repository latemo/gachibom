import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from src.place_locations import build_place_location_index


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class PlaceLocationTests(unittest.TestCase):
    def test_location_overrides_match_schema(self):
        overrides = load_json(ROOT / "data" / "place_location_overrides.json")
        schema = load_json(ROOT / "data" / "schemas" / "place_location_overrides.schema.json")

        self.assertEqual(list(Draft202012Validator(schema).iter_errors(overrides)), [])

    def test_build_place_location_index_uses_roadview_centroid_and_manual_override(self):
        places = load_json(ROOT / "data" / "jeju_accessible_spots.json")
        metadata = load_json(ROOT / "data" / "roadview_image_metadata.json")
        overrides = load_json(ROOT / "data" / "place_location_overrides.json")["items"]

        location_index = build_place_location_index(
            places,
            roadview_metadata=metadata,
            overrides=overrides,
        )

        literature = location_index["jeju_indoor_literature_022"]
        self.assertEqual(literature["source"], "roadview_image_metadata_centroid")
        self.assertEqual(literature["matched_name"], "제주문학관")
        self.assertGreater(literature["evidence_count"], 1)
        self.assertAlmostEqual(literature["latitude"], 33.4813072, places=5)

        icc = location_index["jeju_indoor_icc_032"]
        self.assertEqual(icc["source"], "manual_public_coordinate")
        self.assertEqual(icc["match_method"], "manual_override")
        self.assertAlmostEqual(icc["latitude"], 33.241364, places=6)
        self.assertAlmostEqual(icc["longitude"], 126.424515, places=6)

    def test_location_index_matches_current_seed_route_places(self):
        places = load_json(ROOT / "data" / "jeju_accessible_spots.json")
        metadata = load_json(ROOT / "data" / "roadview_image_metadata.json")
        overrides = load_json(ROOT / "data" / "place_location_overrides.json")["items"]
        seed = load_json(ROOT / "web" / "data" / "app_recommendation_seed.json")
        route_spot_ids = {
            place["spot_id"]
            for scenario in seed["scenarios"]
            for place in scenario["places"]
        }

        location_index = build_place_location_index(
            places,
            roadview_metadata=metadata,
            overrides=overrides,
        )

        self.assertTrue(route_spot_ids)
        self.assertTrue(route_spot_ids.issubset(location_index.keys()))


if __name__ == "__main__":
    unittest.main()
