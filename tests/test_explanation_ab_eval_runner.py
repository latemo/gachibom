from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.run_explanation_ab_eval import (
    build_jobs,
    load_case_document,
    load_seed,
    main,
    prepare_cases,
    render_review_csv,
    run_evaluation_jobs,
)
from src.help_chatbot_service import (
    HELP_CHATBOT_EXCLUSION_RULE_VERSION,
    HELP_CHATBOT_MODE_RULE_VERSION,
    HELP_CHATBOT_PRE_VISIT_RULE_VERSION,
)


class FakeHelpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, str]] = []

    def generate_reply(self, context, *, model):
        self.calls.append((context, model))
        arm = "after" if "recommendation_context" in context else "before"
        return {
            "answer": f"{arm} answer",
            "followups": [],
            "handoff_checklist": ["공식 정보 확인"],
        }


class FlakyHelpClient(FakeHelpClient):
    def generate_reply(self, context, *, model):
        self.calls.append((context, model))
        if len(self.calls) == 1:
            raise ValueError("temporary malformed response")
        arm = "after" if "recommendation_context" in context else "before"
        return {"answer": f"{arm} answer", "followups": [], "handoff_checklist": []}


def sample_seed() -> dict:
    return {
        "generated_at": "2026-07-12",
        "scenarios": [
            {
                "id": "wheelchair_access",
                "title": "휠체어 접근 코스",
                "traveler_summary": {
                    "traveler_type": ["wheelchair_user"],
                    "required_accessibility": ["장애인 화장실"],
                },
                "recommendation": {
                    "course": {
                        "title": "휠체어 접근 코스",
                        "summary": "접근 정보를 확인한 코스",
                        "pace": "slow",
                        "route": [{"order": 1, "spot_id": "spot-1", "name": "제주문학관"}],
                    },
                    "score": {"total": 84, "grade": "B", "confidence": "high"},
                    "fit_reasons": ["휠체어 접근 정보가 있습니다."],
                    "deduction_reasons": ["방문 전 운영 여부를 확인해야 합니다."],
                    "check_before_visit": ["장애인 화장실 운영 여부"],
                },
                "places": [
                    {
                        "spot_id": "spot-1",
                        "name": "제주문학관",
                        "score": {"total": 84, "grade": "B", "confidence": "high"},
                        "fit_reasons": ["휠체어 접근 정보가 있습니다."],
                        "deduction_reasons": [],
                        "check_before_visit": ["장애인 화장실 운영 여부"],
                        "source_summary": [
                            {"title": "공식 접근성 정보", "url": "https://example.org/place", "status": "verified"}
                        ],
                        "verification_status": "verified",
                    }
                ],
            }
        ],
    }


def sample_context() -> dict:
    return {
        "mode": "static",
        "generated_at": "2026-07-12",
        "engine": {"scoring": "precomputed_recommendation_seed"},
        "traveler_summary": {
            "traveler_type": ["wheelchair_user"],
            "required_accessibility": ["장애인 화장실"],
        },
        "recommendation": {
            "course": {
                "title": "휠체어 접근 코스",
                "route": [{"order": 1, "spot_id": "spot-1", "name": "제주문학관"}],
            },
            "score": {"total": 84, "grade": "B", "confidence": "high"},
            "fit_reasons": ["휠체어 접근 정보가 있습니다."],
            "deduction_reasons": [],
            "check_before_visit": ["장애인 화장실 운영 여부"],
        },
        "selected_place": {
            "spot_id": "spot-1",
            "name": "제주문학관",
            "score": {"total": 84, "grade": "B", "confidence": "high"},
            "fit_reasons": ["휠체어 접근 정보가 있습니다."],
            "check_before_visit": ["장애인 화장실 운영 여부"],
            "source_summary": [
                {"title": "공식 접근성 정보", "url": "https://example.org/place", "status": "verified"}
            ],
            "verification_status": "verified",
            "blocked": False,
        },
    }


def sample_case(*, embedded_context: bool = True) -> dict:
    case = {
        "id": "wheelchair_access_reason",
        "scenario_id": "wheelchair_access",
        "question_type": "recommendation_reason",
        "question": "왜 제주문학관이 추천됐나요?",
        "selected_place_id": "spot-1",
        "expected_mode": "static",
        "expected_evidence": ["휠체어 접근 정보"],
    }
    if embedded_context:
        case["recommendation_context"] = sample_context()
    return case


class ExplanationAbEvalRunnerTests(unittest.TestCase):
    def test_before_omits_context_and_after_uses_same_client_and_model(self):
        cases = prepare_cases([sample_case()], sample_seed())
        client = FakeHelpClient()

        records = run_evaluation_jobs(
            cases,
            model="gpt-5-mini",
            client=client,
            max_workers=1,
        )

        self.assertEqual([record["variant"] for record in records], ["before", "after"])
        self.assertTrue(all(record["status"] == "success" for record in records))
        self.assertEqual(len(client.calls), 2)
        self.assertNotIn("recommendation_context", client.calls[0][0])
        self.assertEqual(client.calls[1][0]["recommendation_context"]["mode"], "static")
        self.assertEqual([call[1] for call in client.calls], ["gpt-5-mini", "gpt-5-mini"])

    def test_context_is_reconstructed_from_seed_for_compatible_case(self):
        prepared = prepare_cases([sample_case(embedded_context=False)], sample_seed())

        context = prepared[0]["recommendation_context"]
        self.assertEqual(context["mode"], "static")
        self.assertEqual(context["recommendation"]["score"]["total"], 84)
        self.assertEqual(context["selected_place"]["spot_id"], "spot-1")

    def test_mode_rule_version_invalidates_only_after_mode_job(self):
        mode_case = sample_case()
        mode_case["question_type"] = "mode_distinction"
        mode_case["question"] = "실시간 계산인가요, 사전 계산인가요?"
        jobs = build_jobs(prepare_cases([mode_case], sample_seed()), "gpt-5-mini")

        self.assertIsNone(jobs[0]["behavior_version"])
        self.assertEqual(jobs[1]["behavior_version"], HELP_CHATBOT_MODE_RULE_VERSION)
        self.assertNotEqual(jobs[1]["signature"], jobs[1]["legacy_signature"])

    def test_pre_visit_rule_version_invalidates_only_after_pre_visit_job(self):
        pre_visit_case = sample_case()
        pre_visit_case["question_type"] = "pre_visit_check"
        pre_visit_case["question"] = "방문 전에 무엇을 확인해야 하나요?"
        jobs = build_jobs(prepare_cases([pre_visit_case], sample_seed()), "gpt-5-mini")

        self.assertIsNone(jobs[0]["behavior_version"])
        self.assertEqual(jobs[1]["behavior_version"], HELP_CHATBOT_PRE_VISIT_RULE_VERSION)
        self.assertNotEqual(jobs[1]["signature"], jobs[1]["legacy_signature"])

    def test_exclusion_rule_version_invalidates_only_after_exclusion_job(self):
        exclusion_case = sample_case()
        exclusion_case["question_type"] = "exclusion_or_alternative"
        exclusion_case["question"] = "어떤 유형의 장소가 대안으로 덜 적합한가요?"
        jobs = build_jobs(prepare_cases([exclusion_case], sample_seed()), "gpt-5-mini")

        self.assertIsNone(jobs[0]["behavior_version"])
        self.assertEqual(jobs[1]["behavior_version"], HELP_CHATBOT_EXCLUSION_RULE_VERSION)
        self.assertNotEqual(jobs[1]["signature"], jobs[1]["legacy_signature"])

    def test_successful_records_are_reused_by_signature(self):
        cases = prepare_cases([sample_case()], sample_seed())
        first_client = FakeHelpClient()
        first = run_evaluation_jobs(cases, model="gpt-5-mini", client=first_client, max_workers=1)
        resumed_client = FakeHelpClient()

        resumed = run_evaluation_jobs(
            cases,
            model="gpt-5-mini",
            client=resumed_client,
            max_workers=1,
            existing_records=first,
        )

        self.assertEqual(resumed_client.calls, [])
        self.assertTrue(all(record["resumed"] for record in resumed))

    def test_legacy_signature_is_migrated_without_new_calls(self):
        cases = prepare_cases([sample_case()], sample_seed())
        jobs = build_jobs(cases, "gpt-5-mini")
        records = run_evaluation_jobs(cases, model="gpt-5-mini", client=FakeHelpClient(), max_workers=1)
        for record, job in zip(records, jobs):
            record["run_signature"] = job["legacy_signature"]
            record.pop("prompt_version", None)
        resumed_client = FakeHelpClient()

        resumed = run_evaluation_jobs(
            cases,
            model="gpt-5-mini",
            client=resumed_client,
            max_workers=1,
            existing_records=records,
        )

        self.assertEqual(resumed_client.calls, [])
        self.assertTrue(all(record["prompt_version"] for record in resumed))
        self.assertEqual([record["run_signature"] for record in resumed], [job["signature"] for job in jobs])

    def test_failed_generation_is_retried_with_bounded_attempts(self):
        cases = prepare_cases([sample_case()], sample_seed())
        client = FlakyHelpClient()

        records = run_evaluation_jobs(
            cases,
            model="gpt-5-mini",
            client=client,
            max_workers=1,
            max_retries=1,
        )

        self.assertTrue(all(record["status"] == "success" for record in records))
        self.assertEqual(records[0]["attempts"], 2)
        self.assertEqual(len(client.calls), 3)

    def test_dry_run_needs_no_api_key_and_writes_no_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases_path = root / "cases.json"
            seed_path = root / "seed.json"
            outputs = [root / "results.json", root / "results.csv", root / "report.md", root / "review.csv"]
            cases_path.write_text(json.dumps({"cases": [sample_case()]}, ensure_ascii=False), encoding="utf-8")
            seed_path.write_text(json.dumps(sample_seed(), ensure_ascii=False), encoding="utf-8")
            stdout = io.StringIO()

            with patch("scripts.run_explanation_ab_eval.openai_help_chatbot_client_from_env") as client_factory:
                with redirect_stdout(stdout):
                    status = main(
                        [
                            "--cases",
                            str(cases_path),
                            "--seed",
                            str(seed_path),
                            "--dry-run",
                            "--output-json",
                            str(outputs[0]),
                            "--output-csv",
                            str(outputs[1]),
                            "--output-md",
                            str(outputs[2]),
                            "--review-csv",
                            str(outputs[3]),
                        ]
                    )

            self.assertEqual(status, 0)
            self.assertIn("dry_run=ok cases=1 calls=2 model=gpt-5-mini", stdout.getvalue())
            client_factory.assert_not_called()
            self.assertTrue(all(not output.exists() for output in outputs))

    def test_non_dry_run_without_key_fails_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases_path = root / "cases.json"
            seed_path = root / "seed.json"
            cases_path.write_text(json.dumps({"cases": [sample_case()]}, ensure_ascii=False), encoding="utf-8")
            seed_path.write_text(json.dumps(sample_seed(), ensure_ascii=False), encoding="utf-8")
            stderr = io.StringIO()

            with patch("scripts.run_explanation_ab_eval.openai_help_chatbot_client_from_env", return_value=None):
                with redirect_stderr(stderr):
                    status = main(["--cases", str(cases_path), "--seed", str(seed_path)])

            self.assertEqual(status, 2)
            self.assertIn("OPENAI_API_KEY is required", stderr.getvalue())

    def test_cli_with_injected_client_writes_all_review_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases_path = root / "cases.json"
            seed_path = root / "seed.json"
            output_json = root / "results.json"
            output_csv = root / "results.csv"
            output_md = root / "report.md"
            review_csv = root / "review.csv"
            cases_path.write_text(json.dumps({"cases": [sample_case()]}, ensure_ascii=False), encoding="utf-8")
            seed_path.write_text(json.dumps(sample_seed(), ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                status = main(
                    [
                        "--cases",
                        str(cases_path),
                        "--seed",
                        str(seed_path),
                        "--output-json",
                        str(output_json),
                        "--output-csv",
                        str(output_csv),
                        "--output-md",
                        str(output_md),
                        "--review-csv",
                        str(review_csv),
                        "--max-workers",
                        "1",
                    ],
                    client=FakeHelpClient(),
                )

            self.assertEqual(status, 0)
            self.assertTrue(all(path.exists() for path in [output_json, output_csv, output_md, review_csv]))
            self.assertIn("before_answer,after_answer", review_csv.read_text(encoding="utf-8"))
            self.assertEqual(len(build_jobs(prepare_cases([sample_case()], sample_seed()), "gpt-5-mini")), 2)

    def test_review_csv_has_blank_human_scoring_columns(self):
        cases = prepare_cases([sample_case()], sample_seed())
        records = run_evaluation_jobs(cases, model="gpt-5-mini", client=FakeHelpClient(), max_workers=1)

        review = render_review_csv(cases, records)

        self.assertIn("before_correctness_1_5", review)
        self.assertIn("before_understanding_1_5", review)
        self.assertIn("before_hallucination_yes_no", review)
        self.assertIn("review_status", review)
        self.assertIn("before answer", review)
        self.assertIn("after answer", review)

    def test_existing_human_review_is_preserved_unless_reset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases_path = root / "cases.json"
            seed_path = root / "seed.json"
            review_csv = root / "review.csv"
            cases_path.write_text(json.dumps({"cases": [sample_case()]}, ensure_ascii=False), encoding="utf-8")
            seed_path.write_text(json.dumps(sample_seed(), ensure_ascii=False), encoding="utf-8")
            review_csv.write_text("reviewer_notes\n사람 검토 완료\n", encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                status = main(
                    [
                        "--cases", str(cases_path),
                        "--seed", str(seed_path),
                        "--output-json", str(root / "results.json"),
                        "--output-csv", str(root / "results.csv"),
                        "--output-md", str(root / "report.md"),
                        "--review-csv", str(review_csv),
                    ],
                    client=FakeHelpClient(),
                )

            self.assertEqual(status, 0)
            self.assertEqual(review_csv.read_text(encoding="utf-8"), "reviewer_notes\n사람 검토 완료\n")

    def test_json_loaders_accept_document_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases_path = root / "cases.json"
            seed_path = root / "seed.json"
            cases_path.write_text(
                json.dumps({"schema_version": "1.0", "case_count": 1, "cases": [sample_case()]}, ensure_ascii=False),
                encoding="utf-8",
            )
            seed_path.write_text(json.dumps(sample_seed(), ensure_ascii=False), encoding="utf-8")

            document, cases = load_case_document(cases_path)
            seed = load_seed(seed_path)

            self.assertEqual(document["case_count"], 1)
            self.assertEqual(cases[0]["id"], "wheelchair_access_reason")
            self.assertEqual(seed["scenarios"][0]["id"], "wheelchair_access")


if __name__ == "__main__":
    unittest.main()
