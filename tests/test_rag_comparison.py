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
)
from src.rag_comparison import (
    BASELINE_STATUS,
    build_rag_comparison_report,
    render_cases_csv,
    render_metrics_csv,
    render_rag_comparison_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_no_rag_report():
    responses = build_no_rag_baseline_responses(generated_at=date(2026, 7, 10))
    return build_no_rag_baseline_validation_report(responses, generated_at=date(2026, 7, 10))


class RagComparisonTests(unittest.TestCase):
    def test_report_marks_no_rag_unmeasured_when_baseline_is_missing(self):
        report = build_rag_comparison_report(
            load_json(ROOT / "data" / "recommendation_case_validation_report.json"),
            load_json(ROOT / "data" / "tourism_weak_recommendation_courses.json"),
            generated_at=date(2026, 7, 10),
        )

        summary = report["summary"]
        self.assertEqual(summary["scenario_cases"], 5)
        self.assertEqual(summary["with_rag_passed_cases"], 5)
        self.assertEqual(summary["with_rag_case_pass_rate"], 1.0)
        self.assertEqual(summary["with_rag_total_checks"], 59)
        self.assertEqual(summary["with_rag_passed_checks"], 59)
        self.assertEqual(summary["with_rag_check_pass_rate"], 1.0)
        self.assertEqual(summary["without_rag_observed_cases"], 0)
        self.assertEqual(summary["without_rag_status"], BASELINE_STATUS)
        self.assertEqual(summary["official_course_slots"]["matched_stops"], 62)
        self.assertEqual(summary["official_course_slots"]["slot_match_rate"], 1.0)

    def test_report_uses_no_rag_baseline_values_when_provided(self):
        report = build_rag_comparison_report(
            load_json(ROOT / "data" / "recommendation_case_validation_report.json"),
            load_json(ROOT / "data" / "tourism_weak_recommendation_courses.json"),
            build_no_rag_report(),
            generated_at=date(2026, 7, 10),
        )

        summary = report["summary"]
        self.assertEqual(summary["scenario_cases"], 5)
        self.assertEqual(summary["with_rag_passed_cases"], 5)
        self.assertEqual(summary["with_rag_passed_checks"], 59)
        self.assertEqual(summary["without_rag_observed_cases"], 5)
        self.assertEqual(summary["without_rag_status"], NO_RAG_STATUS)
        self.assertEqual(summary["without_rag_passed_cases"], 0)
        self.assertEqual(summary["without_rag_passed_checks"], 5)
        self.assertEqual(summary["without_rag_total_checks"], 59)
        self.assertEqual(summary["without_rag_check_pass_rate"], 0.0847)

    def test_case_rows_include_observed_no_rag_failures(self):
        report = build_rag_comparison_report(
            load_json(ROOT / "data" / "recommendation_case_validation_report.json"),
            load_json(ROOT / "data" / "tourism_weak_recommendation_courses.json"),
            build_no_rag_report(),
            generated_at=date(2026, 7, 10),
        )

        self.assertEqual(len(report["cases"]), 5)
        for case in report["cases"]:
            self.assertEqual(case["without_rag_baseline"]["status"], "실패")
            self.assertTrue(case["without_rag_baseline"]["observed"])
            self.assertTrue(case["without_rag_baseline"]["comparable"])
            self.assertEqual(case["without_rag_baseline"]["passed_checks"], 1)
            self.assertGreater(len(case["without_rag_baseline"]["expected_failure_modes"]), 0)
            self.assertGreater(len(case["without_rag_baseline"]["failed_check_names"]), 0)

    def test_renderers_export_metrics_cases_and_markdown(self):
        report = build_rag_comparison_report(
            load_json(ROOT / "data" / "recommendation_case_validation_report.json"),
            load_json(ROOT / "data" / "tourism_weak_recommendation_courses.json"),
            build_no_rag_report(),
            generated_at=date(2026, 7, 10),
        )

        metrics_csv = render_metrics_csv(report)
        cases_csv = render_cases_csv(report)
        markdown = render_rag_comparison_markdown(report)

        self.assertIn("metric_id,label,validation_target", metrics_csv)
        self.assertIn("without_rag_passed_checks", cases_csv)
        self.assertIn("동문재래시장", cases_csv)
        self.assertIn("# RAG 사용/미사용 비교 데이터", markdown)
        self.assertIn("5/59 체크 통과", markdown)

    def test_cli_writes_all_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            no_rag_validation = temp_path / "no_rag_validation.json"
            output_json = temp_path / "rag_comparison.json"
            output_metrics_csv = temp_path / "rag_metrics.csv"
            output_cases_csv = temp_path / "rag_cases.csv"
            output_md = temp_path / "rag_comparison.md"
            no_rag_validation.write_text(
                json.dumps(build_no_rag_report(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_rag_comparison_report.py"),
                    "--case-validation",
                    str(ROOT / "data" / "recommendation_case_validation_report.json"),
                    "--tourism-weak-courses",
                    str(ROOT / "data" / "tourism_weak_recommendation_courses.json"),
                    "--no-rag-validation",
                    str(no_rag_validation),
                    "--output-json",
                    str(output_json),
                    "--output-metrics-csv",
                    str(output_metrics_csv),
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
            self.assertIn("without_rag_checks:5/59", result.stdout)
            self.assertTrue(output_json.exists())
            self.assertTrue(output_metrics_csv.exists())
            self.assertTrue(output_cases_csv.exists())
            self.assertTrue(output_md.exists())
            self.assertIn("RAG 사용/미사용 비교 데이터", output_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
