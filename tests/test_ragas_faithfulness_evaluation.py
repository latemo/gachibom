import unittest
from copy import deepcopy
from datetime import date

from src.ragas_faithfulness_evaluation import (
    RagasEvaluationInputError,
    build_faithfulness_report,
    prepare_faithfulness_samples,
    ragas_dataset_rows,
)


def case_document():
    return {
        "cases": [
            {
                "id": "case_1",
                "scenario_id": "wheelchair_access",
                "question_type": "recommendation_reason",
                "question": "왜 추천했나요?",
                "selected_place_name": "제주문학관",
                "recommendation_context": {
                    "traveler_summary": {"required_accessibility": ["주차"]},
                    "selected_place": {"name": "제주문학관"},
                    "recommendation": {
                        "course": {"route": [{"spot_id": "place_1", "name": "제주문학관"}]}
                    },
                },
                "expected": {
                    "score": {"total": 90},
                    "checks": ["주차"],
                    "allowed_course_place_names": ["제주문학관"],
                    "reasons": {"fit": ["실내 휴식 가능"]},
                },
                "expected_evidence": ["실내 휴식 가능"],
                "expected_user_conditions": [{"label": "필수", "terms": ["주차"]}],
            }
        ]
    }


def result_document():
    return {
        "records": [
            {
                "case_id": "case_1",
                "condition": "after",
                "status": "success",
                "response": {"answer": "제주문학관은 실내 휴식 근거가 있어 추천됐습니다."},
            },
            {
                "case_id": "case_1",
                "condition": "before",
                "status": "success",
                "response": {"answer": "제주문학관을 추천합니다."},
            },
        ]
    }


class RagasFaithfulnessEvaluationTests(unittest.TestCase):
    def test_prepares_after_sample_with_bounded_evidence(self):
        samples = prepare_faithfulness_samples(case_document(), result_document())

        self.assertEqual(len(samples), 1)
        sample = samples[0]
        self.assertEqual(sample["sample_id"], "case_1__after")
        self.assertEqual(sample["condition"], "after")
        self.assertEqual(len(sample["retrieved_contexts"]), 3)
        self.assertIn("제주문학관", " ".join(sample["retrieved_contexts"]))
        self.assertEqual(len(sample["run_signature"]), 64)
        self.assertEqual(set(ragas_dataset_rows(samples)[0]), {"user_input", "retrieved_contexts", "response", "reference"})

    def test_can_prepare_both_conditions_without_duplicate_ids(self):
        samples = prepare_faithfulness_samples(
            case_document(), result_document(), conditions=("before", "after")
        )

        self.assertEqual({sample["sample_id"] for sample in samples}, {"case_1__before", "case_1__after"})

    def test_mode_question_includes_mode_source_and_meaning(self):
        cases = deepcopy(case_document())
        cases["cases"][0]["question_type"] = "mode_distinction"
        cases["cases"][0]["recommendation_context"]["mode"] = "static"

        sample = prepare_faithfulness_samples(cases, result_document())[0]
        evidence = " ".join(sample["retrieved_contexts"])

        self.assertEqual(len(sample["retrieved_contexts"]), 4)
        self.assertIn('\"mode\":\"static\"', evidence)
        self.assertIn("실시간 개인별 재계산이 아닙니다", evidence)

    def test_rejects_unknown_case_records(self):
        document = result_document()
        document["records"][0]["case_id"] = "missing"
        with self.assertRaisesRegex(RagasEvaluationInputError, "unknown case"):
            prepare_faithfulness_samples(case_document(), document)

    def test_report_is_provisional_and_surfaces_low_scores(self):
        samples = prepare_faithfulness_samples(
            case_document(), result_document(), conditions=("before", "after")
        )
        scores = [
            {"sample_id": "case_1__after", "status": "success", "faithfulness": 1.0},
            {"sample_id": "case_1__before", "status": "success", "faithfulness": 0.5},
        ]

        report = build_faithfulness_report(
            samples,
            scores,
            generated_at=date(2026, 7, 15),
            model="gpt-5-mini",
            ragas_version="0.4.3",
            threshold=0.95,
        )

        self.assertEqual(report["status"], "complete_provisional")
        self.assertFalse(report["reportable_as_final"])
        self.assertEqual(report["summary"]["mean"], 0.75)
        self.assertEqual(report["summary"]["pass_rate"], 0.5)
        self.assertEqual(report["lowest_cases"][0]["sample_id"], "case_1__before")


if __name__ == "__main__":
    unittest.main()
