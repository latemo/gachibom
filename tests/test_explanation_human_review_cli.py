from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.build_blind_explanation_review import main as build_main
from scripts.build_explanation_review_workbooks import main as build_xlsx_main
from scripts.summarize_explanation_human_review import main as summarize_main
from src.explanation_review_workbook import write_explanation_review_workbook


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "explanation_eval_results.json"
CASES = ROOT / "data" / "explanation_eval_cases.json"


class ExplanationHumanReviewCliTests(unittest.TestCase):
    def test_builder_writes_balanced_packet_and_protects_existing_mapping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_csv = root / "review.csv"
            key_json = root / "key.json"
            args = self._build_args(review_csv, key_json)

            with redirect_stdout(io.StringIO()):
                status = build_main(args, seed="fixed-cli-seed")

            self.assertEqual(status, 0)
            rows = self._read_csv(review_csv)
            key = json.loads(key_json.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 30)
            self.assertEqual(key["answer_a_counts"], {"before": 15, "after": 15})
            self.assertTrue(all(row["immutable_fingerprint"] for row in rows))

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                second_status = build_main(args, seed="different-seed")
            self.assertEqual(second_status, 2)
            self.assertIn("refusing to replace", stderr.getvalue())

            with redirect_stdout(io.StringIO()):
                dry_run_status = build_main([*args, "--dry-run"], seed="different-seed")
            self.assertEqual(dry_run_status, 0)

    def test_pending_packet_generates_pending_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_csv = root / "review.csv"
            key_json = root / "key.json"
            output_json = root / "summary.json"
            output_md = root / "summary.md"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(build_main(self._build_args(review_csv, key_json), seed="pending"), 0)
                status = summarize_main(
                    self._summary_args([review_csv], key_json, output_json, output_md)
                )

            self.assertEqual(status, 0)
            report = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(report["human_review_status"], "pending")
            self.assertEqual(report["gate"]["status"], "pending")
            self.assertEqual(report["coverage"]["completed_review_count"], 0)
            self.assertIn("사람 검토 상태: **pending**", output_md.read_text(encoding="utf-8"))

    def test_three_complete_reviews_are_deblinded_and_pass_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_csv = root / "master.csv"
            key_json = root / "key.json"
            output_json = root / "summary.json"
            output_md = root / "summary.md"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(build_main(self._build_args(master_csv, key_json), seed="complete"), 0)

            key = json.loads(key_json.read_text(encoding="utf-8"))
            assignments = {item["blind_id"]: item for item in key["assignments"]}
            review_files = []
            for reviewer_number in range(1, 4):
                rows = self._read_csv(master_csv)
                for row in rows:
                    assignment = assignments[row["blind_id"]]
                    for position in ("a", "b"):
                        variant = assignment[f"answer_{position}_variant"]
                        rating = "5" if variant == "after" else "4"
                        row[f"answer_{position}_correctness_1_5"] = rating
                        row[f"answer_{position}_understanding_1_5"] = rating
                        row[f"answer_{position}_decision_help_1_5"] = rating
                        row[f"answer_{position}_hallucination_yes_no"] = "no"
                        row[f"answer_{position}_safety_issue_yes_no"] = "no"
                        if row["previsit_applicable"] == "yes":
                            row[f"answer_{position}_previsit_clarity_yes_no"] = "yes"
                    row["preference"] = (
                        "A" if assignment["answer_a_variant"] == "after" else "B"
                    )
                    row["reviewer_id"] = f"R{reviewer_number:02d}"
                    row["review_status"] = "complete"
                path = root / f"reviewer-{reviewer_number}.csv"
                self._write_csv(path, rows)
                review_files.append(path)

            with redirect_stdout(io.StringIO()):
                status = summarize_main(
                    self._summary_args(review_files, key_json, output_json, output_md)
                )

            self.assertEqual(status, 0)
            report = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(report["coverage"]["completed_review_count"], 90)
            self.assertEqual(report["human_review_status"], "complete")
            self.assertEqual(report["summary"]["preference"]["after_non_tie_win_rate"], 1.0)
            self.assertEqual(report["gate"]["status"], "passed")

    def test_summarizer_rejects_tampered_answer_and_legacy_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_csv = root / "review.csv"
            key_json = root / "key.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(build_main(self._build_args(review_csv, key_json), seed="tamper"), 0)

            rows = self._read_csv(review_csv)
            rows[0]["answer_a"] += " 변조"
            self._write_csv(review_csv, rows)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = summarize_main(
                    self._summary_args(
                        [review_csv], key_json, root / "bad.json", root / "bad.md"
                    )
                )
            self.assertEqual(status, 2)
            self.assertIn("fingerprint", stderr.getvalue())

            legacy = root / "legacy.csv"
            legacy.write_text("case_id,before_answer,after_answer\ncase-1,a,b\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                legacy_status = summarize_main(
                    self._summary_args(
                        [legacy], key_json, root / "legacy.json", root / "legacy.md"
                    )
                )
            self.assertEqual(legacy_status, 2)
            self.assertIn("legacy unblinded", stderr.getvalue())

    def test_xlsx_builder_creates_three_reviewer_files_and_protects_existing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_csv = root / "master.csv"
            key_json = root / "key.json"
            output_dir = root / "workbooks"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    build_main(self._build_args(master_csv, key_json), seed="xlsx-builder"),
                    0,
                )
            args = [
                "--master-csv", str(master_csv),
                "--output-dir", str(output_dir),
            ]
            with redirect_stdout(io.StringIO()):
                status = build_xlsx_main(args)

            self.assertEqual(status, 0)
            paths = sorted(output_dir.glob("*.xlsx"))
            self.assertEqual([path.stem[-3:] for path in paths], ["R01", "R02", "R03"])
            self.assertTrue(all(path.stat().st_size > 10_000 for path in paths))

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                second_status = build_xlsx_main(args)
            self.assertEqual(second_status, 2)
            self.assertIn("refusing to replace", stderr.getvalue())

    def test_three_completed_xlsx_files_pass_existing_human_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master_csv = root / "master.csv"
            key_json = root / "key.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    build_main(self._build_args(master_csv, key_json), seed="xlsx-gate"),
                    0,
                )
            master_rows = self._read_csv(master_csv)
            key = json.loads(key_json.read_text(encoding="utf-8"))
            assignments = {item["blind_id"]: item for item in key["assignments"]}
            review_specs: list[str] = []
            for reviewer_number in range(1, 4):
                reviewer_id = f"R{reviewer_number:02d}"
                rows = [dict(row) for row in master_rows]
                for row in rows:
                    assignment = assignments[row["blind_id"]]
                    for position in ("a", "b"):
                        variant = assignment[f"answer_{position}_variant"]
                        rating = "5" if variant == "after" else "4"
                        for dimension in ("correctness", "understanding", "decision_help"):
                            row[f"answer_{position}_{dimension}_1_5"] = rating
                        row[f"answer_{position}_hallucination_yes_no"] = "no"
                        row[f"answer_{position}_safety_issue_yes_no"] = "no"
                        row[f"answer_{position}_previsit_clarity_yes_no"] = (
                            "yes" if row["previsit_applicable"] == "yes" else "n/a"
                        )
                    row["preference"] = (
                        "A" if assignment["answer_a_variant"] == "after" else "B"
                    )
                workbook = root / f"{reviewer_id}.xlsx"
                write_explanation_review_workbook(workbook, rows, reviewer_id=reviewer_id)
                review_specs.extend(["--review-xlsx", f"{reviewer_id}={workbook}"])

            output_json = root / "summary.json"
            output_md = root / "summary.md"
            args = [
                *review_specs,
                "--master-review-csv", str(master_csv),
                "--key", str(key_json),
                "--automatic-results", str(RESULTS),
                "--output-json", str(output_json),
                "--output-md", str(output_md),
            ]
            with redirect_stdout(io.StringIO()):
                status = summarize_main(args)

            self.assertEqual(status, 0)
            report = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(report["coverage"]["completed_review_count"], 90)
            self.assertEqual(report["gate"]["status"], "passed")

    @staticmethod
    def _build_args(review_csv: Path, key_json: Path) -> list[str]:
        return [
            "--results", str(RESULTS),
            "--cases", str(CASES),
            "--output", str(review_csv),
            "--key-output", str(key_json),
        ]

    @staticmethod
    def _summary_args(
        review_files: list[Path], key_json: Path, output_json: Path, output_md: Path
    ) -> list[str]:
        args: list[str] = []
        for path in review_files:
            args.extend(["--review-csv", str(path)])
        args.extend(
            [
                "--key", str(key_json),
                "--automatic-results", str(RESULTS),
                "--output-json", str(output_json),
                "--output-md", str(output_md),
            ]
        )
        return args

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
