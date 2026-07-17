import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

from src.rag_goldset import build_draft_goldset
from src.rag_goldset_evaluation import GoldsetEvaluationError, build_goldset_evaluation_report


ROOT = Path(__file__).resolve().parents[1]


def approved_goldset():
    document = build_draft_goldset(generated_at=date(2026, 7, 15))
    document["cases"] = deepcopy(document["cases"][:2])
    document["status"] = "approved"
    first, second = document["cases"]
    first["review"]["status"] = "approved"
    first["review"]["reviewer_ids"] = ["reviewer_a", "reviewer_b"]
    first["review"]["adjudicated_by"] = "reviewer_c"
    first["expected"]["relevant_place_ids"] = ["place_a", "place_b"]
    second["review"]["status"] = "approved"
    second["review"]["reviewer_ids"] = ["reviewer_a", "reviewer_b"]
    second["review"]["adjudicated_by"] = "reviewer_c"
    second["expected"]["relevant_place_ids"] = ["place_c"]
    return document


def record(case_id, system, places, *, supported=(True,), violations=(), status="success", repetition=1):
    return {
        "case_id": case_id,
        "system": system,
        "repetition": repetition,
        "status": status,
        "ranked_place_ids": list(places),
        "claims": [{"text": f"claim-{index}", "supported": value} for index, value in enumerate(supported)],
        "hard_constraint_violations": list(violations),
    }


class RagGoldsetEvaluationTests(unittest.TestCase):
    def test_draft_goldset_blocks_metrics_instead_of_reporting_zero(self):
        report = build_goldset_evaluation_report(
            build_draft_goldset(generated_at=date(2026, 7, 15)),
            [],
            generated_at=date(2026, 7, 15),
        )

        self.assertEqual(report["status"], "blocked_pending_human_review")
        self.assertFalse(report["reportable"])
        self.assertEqual(report["coverage"]["approved_cases"], 0)
        self.assertEqual(report["systems"], {})

    def test_scores_recall_grounding_and_hard_constraint_gate(self):
        goldset = approved_goldset()
        records = []
        for system in ("gpt_only", "rule_based", "hybrid"):
            records.extend(
                [
                    record("wheelchair_01", system, ["place_a", "other"], supported=(True, True)),
                    record("wheelchair_02", system, ["place_c"], supported=(True, False)),
                ]
            )
        records[-1]["hard_constraint_violations"] = ["필수 주차 조건 위반"]

        report = build_goldset_evaluation_report(goldset, records, generated_at=date(2026, 7, 15))

        self.assertTrue(report["reportable"])
        self.assertEqual(report["systems"]["rule_based"]["metrics"]["recall_at_4"], 0.75)
        self.assertEqual(report["systems"]["rule_based"]["metrics"]["grounded_claim_rate"], 0.75)
        self.assertEqual(report["systems"]["rule_based"]["metrics"]["hard_constraint_violation_rate"], 0.0)
        self.assertFalse(report["systems"]["hybrid"]["release_ready"])

    def test_rejects_unknown_or_unapproved_case_records(self):
        with self.assertRaisesRegex(GoldsetEvaluationError, "unapproved or unknown"):
            build_goldset_evaluation_report(
                approved_goldset(),
                [record("missing_case", "rule_based", [])],
                generated_at=date(2026, 7, 15),
            )

    def test_cli_writes_blocked_report_for_current_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            goldset_path = Path(temp_dir) / "goldset.json"
            output_path = Path(temp_dir) / "report.json"
            goldset_path.write_text(
                json.dumps(build_draft_goldset(generated_at=date(2026, 7, 15)), ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "score_rag_goldset_runs.py"),
                    "--goldset",
                    str(goldset_path),
                    "--runs",
                    str(Path(temp_dir) / "missing.jsonl"),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-15",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("status=blocked_pending_human_review", result.stdout)
            self.assertFalse(json.loads(output_path.read_text(encoding="utf-8"))["reportable"])


if __name__ == "__main__":
    unittest.main()
