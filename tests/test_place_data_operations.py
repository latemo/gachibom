import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.place_data_operations import build_place_data_operations_summary


ROOT = Path(__file__).resolve().parents[1]


def place_card(index: int, *, status: str = "active", verification_status: str = "partial") -> dict:
    return {
        "id": f"jeju_test_place_{index:03d}",
        "name": f"테스트 장소 {index}",
        "region": "제주시",
        "category": "indoor" if index != 3 else "restaurant",
        "status": status,
        "sources": [{"title": "공식 출처", "url": "https://example.com", "type": "public_agency"}],
        "safety_notes": ["방문 전 공식 정보 확인"],
        "verification": {"status": verification_status, "checked_at": "2026-07-08"},
        "accessibility": {
            "wheelchair_access": {"state": "yes"},
            "accessible_toilet": {"state": "yes"},
            "parking": {"state": "partial"},
            "slope_or_stairs": {"state": "needs_check"},
        },
    }


def situation_rules() -> list[dict]:
    return [
        {
            "id": "diet_restriction_no_food",
            "description": "음식 제한",
            "trigger_terms": ["식당 제외", "음식 제한"],
            "exclude_categories": ["restaurant"],
            "penalize_categories": ["cafe"],
            "check_before_visit": ["식사 장소 제외 여부"],
        }
    ]


def raw_catalog_items() -> list[dict]:
    return [
        {
            "catalog_id": "catalog_indoor_11111111",
            "name": "테스트 문학관",
            "category": "indoor",
            "status": "active",
            "matching": {
                "accessibility_card_id": "jeju_test_place_001",
                "match_status": "matched",
                "match_confidence": 1.0,
            },
        },
        {
            "catalog_id": "catalog_sea_22222222",
            "name": "테스트 해변",
            "category": "sea",
            "status": "active",
            "matching": {
                "accessibility_card_id": None,
                "match_status": "unmatched",
                "match_confidence": 0,
            },
        },
    ]


class PlaceDataOperationsTests(unittest.TestCase):
    def test_build_place_data_operations_summary_matches_schema(self):
        places = [
            place_card(1, verification_status="verified"),
            place_card(2, verification_status="partial"),
            place_card(3, verification_status="needs_check"),
            place_card(4, status="hidden", verification_status="verified"),
        ]

        summary = build_place_data_operations_summary(
            places,
            situation_rules(),
            raw_catalog_items=raw_catalog_items(),
            generated_at=date(2026, 7, 9),
        )

        self.assertEqual(summary["summary"]["total_places"], 4)
        self.assertEqual(summary["summary"]["public_candidate_places"], 2)
        self.assertEqual(summary["summary"]["review_only_places"], 1)
        self.assertEqual(summary["summary"]["blocked_from_default_recommendation"], 2)
        self.assertEqual(summary["counts"]["by_category"]["restaurant"], 1)
        self.assertEqual(summary["raw_catalog"]["total_items"], 2)
        self.assertEqual(summary["raw_catalog"]["matched_items"], 1)
        self.assertEqual(summary["raw_catalog"]["unmatched_items"], 1)
        self.assertEqual(summary["scenario_rule_summary"][0]["exclude_categories"], ["restaurant"])

        schema = json.loads(
            (ROOT / "data" / "schemas" / "place_data_operations_summary.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(summary)), [])

    def test_build_place_data_operations_summary_cli_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            places_path = temp_path / "places.json"
            rules_path = temp_path / "rules.json"
            catalog_path = temp_path / "catalog.json"
            output_path = temp_path / "place_data_operations_summary.json"
            places_path.write_text(json.dumps([place_card(1)], ensure_ascii=False), encoding="utf-8")
            rules_path.write_text(json.dumps(situation_rules(), ensure_ascii=False), encoding="utf-8")
            catalog_path.write_text(json.dumps(raw_catalog_items(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_place_data_operations_summary.py"),
                    "--places",
                    str(places_path),
                    "--situation-rules",
                    str(rules_path),
                    "--raw-catalog",
                    str(catalog_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-09",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("public_candidates:1", result.stdout)
            self.assertIn("raw_catalog:2", result.stdout)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8"))["generated_at"],
                "2026-07-09",
            )


if __name__ == "__main__":
    unittest.main()
