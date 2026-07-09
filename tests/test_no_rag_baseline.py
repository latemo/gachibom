import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.no_rag_baseline import (
    NO_RAG_STATUS,
    build_no_rag_baseline_responses,
    build_no_rag_baseline_validation_report,
    render_no_rag_baseline_markdown,
    render_no_rag_cases_csv,
)


ROOT = Path(__file__).resolve().parents[1]


class NoRagBaselineTests(unittest.TestCase):
    def test_baseline_responses_are_marked_as_no_rag_fixture(self):
        responses = build_no_rag_baseline_responses(generated_at=date(2026, 7, 10))

        self.assertFalse(responses["method"]["rag_used"])
        self.assertEqual(responses["method"]["status"], NO_RAG_STATUS)
        self.assertEqual(len(responses["cases"]), 5)
        self.assertIn("raw_response", responses["cases"][0])

    def test_validation_scores_no_rag_baseline_with_same_case_counts(self):
        responses = build_no_rag_baseline_responses(generated_at=date(2026, 7, 10))
        report = build_no_rag_baseline_validation_report(responses, generated_at=date(2026, 7, 10))

        self.assertEqual(report["summary"]["total_cases"], 5)
        self.assertEqual(report["summary"]["passed_cases"], 0)
        self.assertEqual(report["summary"]["failed_cases"], 5)
        self.assertEqual(report["summary"]["total_checks"], 59)
        self.assertEqual(report["summary"]["passed_checks"], 5)
        self.assertEqual(report["summary"]["check_pass_rate"], 0.0847)
        self.assertTrue(all(case["status"] == "실패" for case in report["cases"]))

    def test_renderers_export_no_rag_review_materials(self):
        responses = build_no_rag_baseline_responses(generated_at=date(2026, 7, 10))
        report = build_no_rag_baseline_validation_report(responses, generated_at=date(2026, 7, 10))

        cases_csv = render_no_rag_cases_csv(report)
        markdown = render_no_rag_baseline_markdown(report)

        self.assertIn("case_id,label,status", cases_csv)
        self.assertIn("recovery_quiet", cases_csv)
        self.assertIn("# 무RAG 기준선 검증 자료", markdown)
        self.assertIn("동문재래시장", markdown)

    def test_cli_writes_no_rag_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_responses = temp_path / "no_rag_responses.json"
            output_json = temp_path / "no_rag_validation.json"
            output_cases_csv = temp_path / "no_rag_cases.csv"
            output_md = temp_path / "no_rag.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_no_rag_baseline_report.py"),
                    "--output-responses",
                    str(output_responses),
                    "--output-json",
                    str(output_json),
                    "--output-cases-csv",
                    str(output_cases_csv),
                    "--output-md",
                    str(output_md),
                    "--generated-at",
                    "2026-07-10",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("checks:5/59", result.stdout)
            self.assertTrue(output_responses.exists())
            self.assertTrue(output_json.exists())
            self.assertTrue(output_cases_csv.exists())
            self.assertTrue(output_md.exists())
            loaded = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(loaded["summary"]["passed_checks"], 5)


if __name__ == "__main__":
    unittest.main()
