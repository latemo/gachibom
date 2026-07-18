import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.ragas_change_tracking import (
    append_history_change,
    build_change_detail_report,
    build_initial_history,
    build_run_snapshot,
    compare_runs,
    parse_dataset_jsonl,
    render_change_detail_markdown,
    render_history_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture(*, scores=(0.5, 0.8), response_suffix="", context_suffix=""):
    dataset = [
        {
            "user_input": "질문 1",
            "response": f"답변 1{response_suffix}",
            "retrieved_contexts": [f"근거 1{context_suffix}"],
            "reference": "기준 1",
        },
        {
            "user_input": "질문 2",
            "response": "답변 2",
            "retrieved_contexts": ["근거 2"],
            "reference": "기준 2",
        },
    ]
    manifest = {
        "samples": [
            {
                "line": 1,
                "sample_id": "scenario_a__mode_distinction__after",
                "case_id": "scenario_a__mode_distinction",
                "condition": "after",
                "question_type": "mode_distinction",
                "run_signature": f"run-a{response_suffix}{context_suffix}",
            },
            {
                "line": 2,
                "sample_id": "scenario_b__recommendation_reason__after",
                "case_id": "scenario_b__recommendation_reason",
                "condition": "after",
                "question_type": "recommendation_reason",
                "run_signature": "run-b",
            },
        ]
    }
    score_document = {
        "ragas_version": "0.4.3",
        "model": "gpt-5-mini",
        "records": [
            {
                "sample_id": manifest["samples"][0]["sample_id"],
                "status": "success",
                "faithfulness": scores[0],
            },
            {
                "sample_id": manifest["samples"][1]["sample_id"],
                "status": "success",
                "faithfulness": scores[1],
            },
        ],
    }
    report = {
        "status": "complete_provisional",
        "reportable_as_final": False,
        "evaluation": {
            "library": "ragas",
            "ragas_version": "0.4.3",
            "metric": "faithfulness",
            "model": "gpt-5-mini",
        },
    }
    return dataset, manifest, score_document, report


def snapshot(run_id, *, scores=(0.5, 0.8), response_suffix="", context_suffix=""):
    dataset, manifest, score_document, report = fixture(
        scores=scores,
        response_suffix=response_suffix,
        context_suffix=context_suffix,
    )
    return build_run_snapshot(
        run_id=run_id,
        recorded_at="2026-07-15T00:00:00Z",
        reason="테스트",
        evidence=["지표 근거"],
        changed_files=["web/app.js"],
        dataset_rows=dataset,
        manifest=manifest,
        scores=score_document,
        report=report,
        source_fingerprints={"data/example.json": "abc"},
        role="baseline" if run_id == "baseline" else "change",
    )


class RagasChangeTrackingTests(unittest.TestCase):
    def test_parses_jsonl_and_builds_component_signatures(self):
        dataset, manifest, scores, report = fixture()
        parsed = parse_dataset_jsonl(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in dataset)
        )
        result = build_run_snapshot(
            run_id="baseline",
            recorded_at="2026-07-15T00:00:00Z",
            reason="기준선",
            evidence=[],
            changed_files=[],
            dataset_rows=parsed,
            manifest=manifest,
            scores=scores,
            report=report,
            source_fingerprints={},
            role="baseline",
        )

        self.assertEqual(result["summary"]["mean"], 0.65)
        self.assertEqual(result["summary"]["thresholds"]["0.80"]["passed"], 1)
        self.assertEqual(result["samples"][0]["scenario_id"], "scenario_a")
        self.assertEqual(result["samples"][0]["content"]["response"], "답변 1")
        self.assertEqual(
            result["samples"][0]["content"]["retrieved_contexts"], ["근거 1"]
        )
        self.assertEqual(len(result["samples"][0]["signatures"]["response"]), 64)

    def test_compares_metrics_content_and_regressions(self):
        before = snapshot("baseline")
        after = snapshot(
            "fix_mode",
            scores=(0.7, 0.75),
            response_suffix=" 수정",
            context_suffix=" 변경",
        )

        comparison = compare_runs(
            before, after, evidence_change_authorized=False
        )

        self.assertEqual(
            comparison["metric_delta"]["summary"]["mean"]["delta"], 0.075
        )
        self.assertEqual(comparison["content_delta"]["response"]["changed_count"], 1)
        self.assertEqual(comparison["content_delta"]["context"]["changed_count"], 1)
        self.assertEqual(comparison["case_delta"]["improved_count"], 1)
        self.assertEqual(comparison["case_delta"]["regressed_count"], 1)
        self.assertFalse(comparison["gates"]["evidence_change_declared"])
        self.assertFalse(comparison["gates"]["no_meaningful_case_regression"])
        self.assertFalse(comparison["gates"]["passed"])

    def test_history_renders_before_after_metrics(self):
        before = snapshot("baseline")
        after = snapshot("fix_mode", scores=(0.7, 0.8), response_suffix=" 수정")
        comparison = compare_runs(before, after, evidence_change_authorized=False)
        history = build_initial_history("runs/baseline.json", before)
        history = append_history_change(
            history,
            previous_run_path="runs/baseline.json",
            current_run_path="runs/fix_mode.json",
            current_snapshot=after,
            comparison=comparison,
        )

        markdown = render_history_markdown(history)

        self.assertIn("fix_mode", markdown)
        self.assertIn("0.6500 → 0.7500", markdown)
        self.assertIn("질문 유형별 평균 변화", markdown)

    def test_builds_self_contained_per_change_report(self):
        before = snapshot("baseline")
        after = snapshot("fix_mode", scores=(0.7, 0.8), response_suffix=" 수정")
        comparison = compare_runs(before, after, evidence_change_authorized=False)
        history = append_history_change(
            build_initial_history("runs/baseline.json", before),
            previous_run_path="runs/baseline.json",
            current_run_path="runs/fix_mode.json",
            current_snapshot=after,
            comparison=comparison,
        )

        report = build_change_detail_report(
            change=history["changes"][0], previous=before, current=after
        )
        markdown = render_change_detail_markdown(report)

        self.assertEqual(report["change_id"], "fix_mode")
        self.assertEqual(len(report["changed_samples"]), 1)
        self.assertEqual(
            report["changed_samples"][0]["before"]["response"], "답변 1"
        )
        self.assertEqual(
            report["changed_samples"][0]["after"]["response"], "답변 1 수정"
        )
        self.assertIn("대표 답변 전후", markdown)

    def test_cli_records_immutable_baseline(self):
        dataset, manifest, scores, report = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            dataset_path = temp / "dataset.jsonl"
            dataset_path.write_text(
                "".join(
                    json.dumps(row, ensure_ascii=False) + "\n" for row in dataset
                ),
                encoding="utf-8",
            )
            paths = {}
            for name, value in (
                ("manifest", manifest),
                ("scores", scores),
                ("report", report),
                ("cases", {"cases": []}),
                ("results", {"records": []}),
            ):
                path = temp / f"{name}.json"
                path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                paths[name] = path
            history = temp / "history.json"
            markdown = temp / "history.md"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "record_ragas_change.py"),
                "--baseline",
                "--change-id",
                "baseline_test",
                "--reason",
                "기준선",
                "--dataset",
                str(dataset_path),
                "--manifest",
                str(paths["manifest"]),
                "--scores",
                str(paths["scores"]),
                "--report",
                str(paths["report"]),
                "--cases",
                str(paths["cases"]),
                "--results",
                str(paths["results"]),
                "--run-root",
                str(temp / "runs"),
                "--history-output",
                str(history),
                "--markdown-output",
                str(markdown),
            ]

            completed = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, check=False
            )
            repeated = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, check=False
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(history.read_text(encoding="utf-8"))["changes"], [])
            self.assertIn("baseline_recorded", completed.stdout)


if __name__ == "__main__":
    unittest.main()
