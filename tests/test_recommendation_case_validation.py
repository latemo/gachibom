import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.recommendation_case_validation import (
    PASS,
    build_recommendation_case_validation_report,
    render_recommendation_case_validation_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


def load_places():
    return json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))


class RecommendationCaseValidationTests(unittest.TestCase):
    def test_case_validation_report_matches_schema_and_passes(self):
        report = build_recommendation_case_validation_report(load_places(), generated_at=date(2026, 7, 9))
        schema = json.loads(
            (ROOT / "data" / "schemas" / "recommendation_case_validation_report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = list(Draft202012Validator(schema).iter_errors(report))
        self.assertEqual(errors, [])
        self.assertEqual(report["summary"]["overall_status"], PASS)
        self.assertEqual(report["summary"]["total_cases"], 5)
        self.assertEqual(report["summary"]["failed_cases"], 0)

    def test_case_validation_enforces_condition_specific_rules(self):
        report = build_recommendation_case_validation_report(load_places(), generated_at=date(2026, 7, 9))
        cases = {case["id"]: case for case in report["cases"]}

        self.assertEqual(cases["stroller_family"]["label"], "아이 동반")
        stroller_categories = {place["category"] for place in cases["stroller_family"]["recommendation"]["route"]}
        self.assertTrue(stroller_categories & {"forest", "rest_area"})

        diet_categories = {place["category"] for place in cases["diet_restricted"]["recommendation"]["route"]}
        self.assertTrue(diet_categories.isdisjoint({"restaurant", "food_market"}))
        self.assertTrue(
            any(candidate["category"] in {"restaurant", "food_market"} for candidate in cases["diet_restricted"]["excluded_candidates"])
        )

        weather_route = cases["weather_sensitive"]["recommendation"]["route"]
        self.assertFalse(any(place["category"] in {"sea", "oreum"} for place in weather_route))
        self.assertFalse(any(place["weather_sensitivity"] == "high" for place in weather_route))

    def test_markdown_is_korean_team_review_table(self):
        report = build_recommendation_case_validation_report(load_places(), generated_at=date(2026, 7, 9))
        markdown = render_recommendation_case_validation_markdown(report)
        self.assertIn("# 추천 상황별 검증표", markdown)
        self.assertIn("아이 동반", markdown)
        self.assertIn("음식 제한", markdown)
        self.assertIn("| 영역 | 항목 | 판정 | 기준 | 실제 |", markdown)

    def test_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_json = Path(temp_dir) / "case_validation.json"
            output_md = Path(temp_dir) / "case_validation.md"
            web_output_json = Path(temp_dir) / "web_case_validation.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_recommendation_case_validation_report.py"),
                    "--places",
                    str(ROOT / "data" / "jeju_accessible_spots.json"),
                    "--output-json",
                    str(output_json),
                    "--output-md",
                    str(output_md),
                    "--web-output-json",
                    str(web_output_json),
                    "--generated-at",
                    "2026-07-09",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("status:통과", result.stdout)
            self.assertTrue(output_json.exists())
            self.assertTrue(output_md.exists())
            self.assertTrue(web_output_json.exists())
            self.assertIn("추천 상황별 검증표", output_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
