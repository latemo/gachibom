import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.rag_goldset import build_draft_goldset, render_goldset_csv


ROOT = Path(__file__).resolve().parents[1]


class RagGoldsetTests(unittest.TestCase):
    def test_draft_has_sixty_unique_stratified_cases(self):
        document = build_draft_goldset(generated_at=date(2026, 7, 15))

        self.assertEqual(document["status"], "draft_pending_human_review")
        self.assertEqual(document["summary"]["case_count"], 60)
        self.assertEqual(document["summary"]["split_counts"], {"dev": 40, "test": 20})
        self.assertEqual(document["summary"]["approved_case_count"], 0)
        self.assertFalse(document["summary"]["reportable"])
        self.assertEqual(len({case["id"] for case in document["cases"]}), 60)

    def test_draft_does_not_pretend_to_have_human_relevance_labels(self):
        document = build_draft_goldset(generated_at=date(2026, 7, 15))

        for case in document["cases"]:
            self.assertEqual(case["review"]["status"], "pending_human_review")
            self.assertEqual(case["review"]["reviewer_ids"], [])
            self.assertEqual(case["expected"]["relevant_place_ids"], [])
            self.assertEqual(case["expected"]["acceptable_place_ids"], [])

    def test_review_csv_contains_all_cases_and_review_columns(self):
        document = build_draft_goldset(generated_at=date(2026, 7, 15))
        rows = list(csv.DictReader(io.StringIO(render_goldset_csv(document))))

        self.assertEqual(len(rows), 60)
        self.assertIn("review_status", rows[0])
        self.assertIn("relevant_place_ids", rows[0])
        self.assertIn("required_evidence_fields", rows[0])

    def test_cli_writes_json_and_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_json = Path(temp_dir) / "goldset.json"
            output_csv = Path(temp_dir) / "goldset.csv"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_rag_goldset_v1.py"),
                    "--generated-at",
                    "2026-07-15",
                    "--output-json",
                    str(output_json),
                    "--output-csv",
                    str(output_csv),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("cases=60, dev=40, test=20", result.stdout)
            self.assertEqual(json.loads(output_json.read_text(encoding="utf-8"))["summary"]["case_count"], 60)
            self.assertEqual(len(list(csv.DictReader(output_csv.read_text(encoding="utf-8-sig").splitlines()))), 60)


if __name__ == "__main__":
    unittest.main()
