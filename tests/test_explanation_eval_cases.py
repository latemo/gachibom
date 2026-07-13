import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.explanation_eval_cases import QUESTION_TYPES, build_explanation_eval_cases
from src.help_chatbot_service import normalize_help_recommendation_context


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "web" / "data" / "app_recommendation_seed.json"


def load_seed():
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


class ExplanationEvalCaseTests(unittest.TestCase):
    def test_builds_six_deterministic_cases_for_each_seed_scenario(self):
        seed = load_seed()
        first = build_explanation_eval_cases(seed)
        self.assertEqual(first, build_explanation_eval_cases(seed))
        self.assertEqual((first["scenario_count"], first["questions_per_scenario"], first["case_count"]), (5, 6, 30))
        for scenario in seed["scenarios"]:
            cases = [case for case in first["cases"] if case["scenario_id"] == scenario["id"]]
            self.assertEqual([case["question_type"] for case in cases], list(QUESTION_TYPES))

    def test_context_and_expected_values_are_grounded_in_seed(self):
        seed = load_seed()
        payload = build_explanation_eval_cases(seed)
        scenario_index = {scenario["id"]: scenario for scenario in seed["scenarios"]}
        for case in payload["cases"]:
            scenario = scenario_index[case["scenario_id"]]
            context = case["recommendation_context"]
            selected = context["selected_place"]
            seed_place = next(p for p in scenario["places"] if p["spot_id"] == selected["spot_id"])
            route_names = [item["name"] for item in context["recommendation"]["course"]["route"]]
            self.assertEqual(context, normalize_help_recommendation_context(context))
            self.assertEqual(context["mode"], "static")
            self.assertEqual(case["expected_score"], seed_place["score"]["total"])
            self.assertEqual(case["calculation_trace"], selected["score"]["calculation_trace"])
            self.assertEqual(case["expected"]["conditions"], context["traveler_summary"])
            self.assertEqual(case["expected"]["allowed_course_place_names"], route_names)
            self.assertEqual(case["supported_place_names"], route_names)
            self.assertTrue(set(route_names).issubset(case["known_place_names"]))

    def test_deduction_question_uses_richest_grounded_place_and_handles_no_deduction(self):
        payload = build_explanation_eval_cases(load_seed())
        cases = {c["scenario_id"]: c for c in payload["cases"] if c["question_type"] == "deduction_reason"}
        self.assertEqual(cases["recovery_quiet"]["selected_place_name"], "제주국제컨벤션센터")
        self.assertEqual(cases["stroller_family"]["selected_place_name"], "서귀포 치유의숲")
        self.assertTrue(cases["recovery_quiet"]["expected"]["reasons"]["deductions"])
        self.assertEqual(cases["weather_sensitive"]["expected"]["reasons"]["deductions"], [])
        self.assertIn("없다면 없다고", cases["weather_sensitive"]["question"])

    def test_exclusion_case_records_candidate_evidence_limit(self):
        payload = build_explanation_eval_cases(load_seed())
        cases = [c for c in payload["cases"] if c["question_type"] == "exclusion_or_alternative"]
        self.assertEqual(len(cases), 5)
        for case in cases:
            self.assertEqual(case["expected"]["excluded_place_names"], [])
            self.assertTrue(case["expected"]["exclusion_basis"])
            self.assertIn("특정 비추천 장소명을 단정하지 않는다", case["expected"]["limitations"][0])

    def test_score_question_does_not_leak_expected_total(self):
        payload = build_explanation_eval_cases(load_seed())
        cases = [c for c in payload["cases"] if c["question_type"] == "score_calculation"]

        for case in cases:
            self.assertNotIn(f"{case['expected_score']}점", case["question"])
            self.assertTrue(case["calculation_trace"])

    def test_cli_prints_and_writes_json(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_explanation_eval_cases.py"), "--seed", str(SEED_PATH), "--compact"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["case_count"], 30)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "cases.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build_explanation_eval_cases.py"), "--seed", str(SEED_PATH), "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("cases:30", result.stdout)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["case_count"], 30)


if __name__ == "__main__":
    unittest.main()
