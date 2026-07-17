import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.rag_evidence_status import build_rag_evidence_status, render_rag_evidence_status_markdown


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


class RagEvidenceStatusTests(unittest.TestCase):
    def build_report(self):
        return build_rag_evidence_status(
            load("rag_comparison_report.json"),
            load("explanation_eval_results.json"),
            load("explanation_eval_human_summary.json"),
            load("rag_goldset_v1.json"),
            load("rag_goldset_evaluation_report.json"),
            generated_at=date(2026, 7, 15),
        )

    def test_separates_policy_fixture_and_gpt_evidence(self):
        report = self.build_report()

        self.assertEqual(report["status"], "evidence_in_progress")
        self.assertEqual(report["current_evidence"]["policy_regression"]["passed_checks"], 59)
        self.assertEqual(report["current_evidence"]["controlled_fixture"]["passed_checks"], 5)
        self.assertEqual(report["current_evidence"]["gpt_explanation_ab"]["record_count"], 60)
        self.assertEqual(
            report["current_evidence"]["gpt_explanation_ab"]["expected_evidence_coverage"]["delta"],
            0.4643,
        )
        self.assertIsNone(report["primary_metrics"]["recall_at_4"]["value"])

    def test_markdown_marks_automatic_metrics_as_provisional(self):
        markdown = render_rag_evidence_status_markdown(self.build_report())

        self.assertIn("48.81% → 95.24%", markdown)
        self.assertIn("자동평가·잠정", markdown)
        self.assertIn("사용 금지 표현: RAG 성능 59/59", markdown)

    def test_cli_writes_current_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_json = Path(temp_dir) / "status.json"
            output_md = Path(temp_dir) / "status.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_rag_evidence_status.py"),
                    "--generated-at",
                    "2026-07-15",
                    "--output-json",
                    str(output_json),
                    "--output-md",
                    str(output_md),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("status=evidence_in_progress", result.stdout)
            self.assertEqual(json.loads(output_json.read_text(encoding="utf-8"))["status"], "evidence_in_progress")
            self.assertIn("RAG 평가 증거 현황", output_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
