import json
import unittest
from datetime import date

from src.explanation_human_evaluation import (
    HumanEvaluationValidationError,
    build_explanation_human_evaluation_report,
    render_explanation_human_evaluation_markdown,
)


def assignment(blind_id="blind-1", case_id="case-1", *, swapped=False):
    return {
        "blind_id": blind_id,
        "case_id": case_id,
        "answer_a_variant": "after" if swapped else "before",
        "answer_b_variant": "before" if swapped else "after",
    }


def key(*assignments):
    return {"source_fingerprint": "sha256:test", "assignments": list(assignments)}


def automatic(score_accuracy=1.0):
    return {
        "summary": {
            "variants": {
                "after": {"metrics": {"score_trace_numeric_accuracy": score_accuracy}}
            }
        }
    }


def review(
    reviewer_id,
    *,
    blind_id="blind-1",
    case_id="case-1",
    question_type="recommendation_reason",
    preference="B",
    a=(3, 3, 3),
    b=(5, 5, 4),
    a_previsit="n/a",
    b_previsit="n/a",
    a_hallucination="no",
    b_hallucination="no",
    a_safety="no",
    b_safety="no",
    status="complete",
):
    return {
        "blind_id": blind_id,
        "case_id": case_id,
        "question_type": question_type,
        "reviewer_id": reviewer_id,
        "review_status": status,
        "preference": preference,
        "answer_a_correctness_1_5": str(a[0]),
        "answer_a_understanding_1_5": str(a[1]),
        "answer_a_decision_help_1_5": str(a[2]),
        "answer_b_correctness_1_5": str(b[0]),
        "answer_b_understanding_1_5": str(b[1]),
        "answer_b_decision_help_1_5": str(b[2]),
        "answer_a_previsit_clarity_yes_no": a_previsit,
        "answer_b_previsit_clarity_yes_no": b_previsit,
        "answer_a_hallucination_yes_no": a_hallucination,
        "answer_b_hallucination_yes_no": b_hallucination,
        "answer_a_safety_issue_yes_no": a_safety,
        "answer_b_safety_issue_yes_no": b_safety,
    }


class ExplanationHumanEvaluationTests(unittest.TestCase):
    def test_deblinds_swapped_answers_and_passes_recommended_gate(self):
        assignments = [
            assignment("blind-1", "case-1"),
            assignment("blind-2", "case-2", swapped=True),
        ]
        rows = []
        for reviewer_id in ("r1", "r2", "r3"):
            rows.append(review(reviewer_id))
            rows.append(
                review(
                    reviewer_id,
                    blind_id="blind-2",
                    case_id="case-2",
                    preference="A",
                    a=(5, 5, 5),
                    b=(3, 3, 3),
                )
            )

        report = build_explanation_human_evaluation_report(
            rows,
            key(*assignments),
            automatic(),
            generated_at=date(2026, 7, 12),
            required_assignment_count=2,
        )

        self.assertEqual(report["human_review_status"], "complete")
        self.assertEqual(report["summary"]["variants"]["after"]["ratings"]["correctness"], 5.0)
        self.assertEqual(report["summary"]["variants"]["before"]["ratings"]["correctness"], 3.0)
        self.assertEqual(report["summary"]["preference"]["after_non_tie_win_rate"], 1.0)
        self.assertEqual(report["summary"]["deltas"]["decision_help"], 1.5)
        self.assertEqual(report["gate"]["status"], "passed")
        self.assertIs(report["gate"]["passed"], True)
        json.dumps(report, ensure_ascii=False)

    def test_incomplete_rows_are_ignored_and_gate_stays_pending(self):
        pending = review("", status="pending")
        for field in list(pending):
            if field.startswith("answer_") or field == "preference":
                pending[field] = ""
        rows = [review("r1"), pending]

        report = build_explanation_human_evaluation_report(
            rows,
            key(assignment()),
            automatic(),
            required_assignment_count=1,
        )

        self.assertEqual(report["coverage"]["completed_review_count"], 1)
        self.assertEqual(report["summary"]["variants"]["after"]["review_count"], 1)
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual(report["gate"]["status"], "pending")
        self.assertIsNone(report["gate"]["passed"])
        self.assertIsNone(report["gate"]["checks"][1]["passed"])

    def test_case_median_then_case_mean_prevents_reviewer_count_bias(self):
        assignments = [assignment("blind-1", "case-1"), assignment("blind-2", "case-2")]
        rows = [
            review("r1", b=(5, 5, 5)),
            review("r2", b=(5, 5, 5)),
            review("r3", b=(1, 1, 1)),
            review("r4", b=(1, 1, 1)),
            review("r5", b=(1, 1, 1)),
            review("r1", blind_id="blind-2", case_id="case-2", b=(5, 5, 5)),
            review("r2", blind_id="blind-2", case_id="case-2", b=(5, 5, 5)),
            review("r3", blind_id="blind-2", case_id="case-2", b=(5, 5, 5)),
        ]

        report = build_explanation_human_evaluation_report(
            rows,
            key(*assignments),
            automatic(),
            required_assignment_count=2,
        )
        after = report["summary"]["variants"]["after"]

        self.assertEqual(after["case_medians"]["case-1"]["correctness"], 1.0)
        self.assertEqual(after["case_medians"]["case-2"]["correctness"], 5.0)
        self.assertEqual(after["ratings"]["correctness"], 3.0)
        self.assertEqual(after["raw_reviewer_means"]["ratings"]["correctness"], 3.5)

    def test_preference_is_majority_vote_by_case_and_tied_top_vote_becomes_tie(self):
        assignments = [assignment("blind-1", "case-1"), assignment("blind-2", "case-2")]
        rows = [
            review("r1", preference="b"),
            review("r2", preference="B"),
            review("r3", preference="A"),
            review("r1", blind_id="blind-2", case_id="case-2", preference="A"),
            review("r2", blind_id="blind-2", case_id="case-2", preference="B"),
            review("r3", blind_id="blind-2", case_id="case-2", preference="tie"),
        ]

        report = build_explanation_human_evaluation_report(
            rows,
            key(*assignments),
            automatic(),
            required_assignment_count=2,
        )
        preference = report["summary"]["preference"]

        self.assertEqual(preference["case_decisions"], {"case-1": "after", "case-2": "tie"})
        self.assertEqual(preference["after_non_tie_win_rate"], 1.0)
        self.assertEqual(preference["tie_rate"], 0.5)

    def test_previsit_is_only_aggregated_for_previsit_questions(self):
        rows = [
            review("r1", a_previsit="yes", b_previsit="no"),
            review("r2", a_previsit="", b_previsit="n/a"),
            review("r3", a_previsit="no", b_previsit="yes"),
        ]
        report = build_explanation_human_evaluation_report(
            rows,
            key(assignment()),
            automatic(),
            required_assignment_count=1,
        )
        self.assertIsNone(
            report["summary"]["variants"]["after"]["rates"]["previsit_clarity_yes_rate"]
        )

        previsit_rows = [
            review("r1", question_type="pre_visit_check", a_previsit="no", b_previsit="yes"),
            review("r2", question_type="pre_visit_check", a_previsit="yes", b_previsit="yes"),
            review("r3", question_type="pre_visit_check", a_previsit="no", b_previsit="yes"),
        ]
        previsit_report = build_explanation_human_evaluation_report(
            previsit_rows,
            key(assignment()),
            automatic(),
            required_assignment_count=1,
        )
        self.assertEqual(
            previsit_report["summary"]["variants"]["after"]["rates"]["previsit_clarity_yes_rate"],
            1.0,
        )

    def test_multi_reviewer_agreement_and_rating_mad_are_reported_per_case(self):
        rows = [
            review("r1", preference="B", a=(2, 3, 4), b=(5, 4, 3)),
            review("r2", preference="B", a=(4, 3, 2), b=(3, 4, 5)),
            review("r3", preference="A", a=(3, 3, 3), b=(4, 4, 4)),
        ]
        report = build_explanation_human_evaluation_report(
            rows,
            key(assignment()),
            automatic(),
            required_assignment_count=1,
        )
        agreement = report["summary"]["inter_rater"]
        case_metric = agreement["case_metrics"]["case-1"]

        self.assertEqual(case_metric["reviewer_pair_count"], 3)
        self.assertEqual(case_metric["preference_exact_agreement"], 0.3333)
        self.assertEqual(agreement["preference_exact_agreement"], 0.3333)
        self.assertGreater(agreement["rating_mean_absolute_difference"]["overall"], 0)

    def test_completed_values_are_strictly_validated(self):
        mutations = [
            ("answer_a_correctness_1_5", "6", "integer from 1 to 5"),
            ("answer_b_understanding_1_5", "4.5", "integer from 1 to 5"),
            ("answer_a_hallucination_yes_no", "maybe", "yes or no"),
            ("answer_b_safety_issue_yes_no", "n/a", "yes or no"),
            ("preference", "after", "A, B, or tie"),
        ]
        for field, value, message in mutations:
            with self.subTest(field=field):
                row = review("r1")
                row[field] = value
                with self.assertRaisesRegex(HumanEvaluationValidationError, message):
                    build_explanation_human_evaluation_report(
                        [row], key(assignment()), automatic(), required_assignment_count=1
                    )

    def test_previsit_completed_row_requires_yes_or_no(self):
        row = review(
            "r1",
            question_type="previsit_check",
            a_previsit="n/a",
            b_previsit="yes",
        )
        with self.assertRaisesRegex(HumanEvaluationValidationError, "must be yes or no"):
            build_explanation_human_evaluation_report(
                [row], key(assignment()), automatic(), required_assignment_count=1
            )

    def test_unknown_assignment_duplicate_reviewer_and_case_mismatch_are_rejected(self):
        with self.assertRaisesRegex(HumanEvaluationValidationError, "unknown blind_id"):
            build_explanation_human_evaluation_report(
                [review("r1", blind_id="missing")],
                key(assignment()),
                automatic(),
                required_assignment_count=1,
            )
        with self.assertRaisesRegex(HumanEvaluationValidationError, "duplicate completed review"):
            build_explanation_human_evaluation_report(
                [review("Reviewer"), review("reviewer")],
                key(assignment()),
                automatic(),
                required_assignment_count=1,
            )
        with self.assertRaisesRegex(HumanEvaluationValidationError, "case_id does not match"):
            build_explanation_human_evaluation_report(
                [review("r1", case_id="wrong")],
                key(assignment()),
                automatic(),
                required_assignment_count=1,
            )

    def test_assignment_count_and_three_reviewer_coverage_are_both_required(self):
        two_reviewers = [review("r1"), review("r2")]
        report = build_explanation_human_evaluation_report(
            two_reviewers,
            key(assignment()),
            automatic(),
            required_assignment_count=1,
        )
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual(report["coverage"]["cases_meeting_min_reviewers"], 0)

        wrong_count = build_explanation_human_evaluation_report(
            [review("r1"), review("r2"), review("r3")],
            key(assignment()),
            automatic(),
        )
        self.assertFalse(wrong_count["coverage"]["assignment_count_matches_requirement"])
        self.assertEqual(wrong_count["gate"]["status"], "pending")

    def test_fingerprint_hook_rejects_mismatch(self):
        with self.assertRaisesRegex(HumanEvaluationValidationError, "source fingerprint mismatch"):
            build_explanation_human_evaluation_report(
                [],
                key(assignment()),
                automatic(),
                required_assignment_count=1,
                fingerprint_validator=lambda deblind, report: False,
            )

        report = build_explanation_human_evaluation_report(
            [],
            key(assignment()),
            automatic(),
            required_assignment_count=1,
            fingerprint_validator=lambda deblind, report: deblind["source_fingerprint"] == "sha256:test",
        )
        self.assertEqual(report["source"]["fingerprint_validation"], "passed")

    def test_immutable_fingerprint_is_checked_for_complete_and_pending_rows(self):
        secured_assignment = assignment()
        secured_assignment["immutable_fingerprint"] = "sha256:immutable"
        completed = review("r1")
        completed["immutable_fingerprint"] = "sha256:wrong"
        with self.assertRaisesRegex(HumanEvaluationValidationError, "immutable_fingerprint"):
            build_explanation_human_evaluation_report(
                [completed],
                key(secured_assignment),
                automatic(),
                required_assignment_count=1,
            )

        pending = review("", status="pending")
        pending["immutable_fingerprint"] = "sha256:immutable"
        report = build_explanation_human_evaluation_report(
            [pending],
            key(secured_assignment),
            automatic(),
            required_assignment_count=1,
            row_fingerprint_validator=lambda row, assignment: row["question_type"] == "recommendation_reason",
        )
        self.assertEqual(report["coverage"]["completed_review_count"], 0)
        self.assertEqual(report["source"]["row_fingerprint_validation"], "recomputed")

        with self.assertRaisesRegex(HumanEvaluationValidationError, "immutable fingerprint validation failed"):
            build_explanation_human_evaluation_report(
                [pending],
                key(secured_assignment),
                automatic(),
                required_assignment_count=1,
                row_fingerprint_validator=lambda row, assignment: False,
            )

    def test_markdown_contains_metrics_agreement_and_pending_notice(self):
        report = build_explanation_human_evaluation_report(
            [review("r1")],
            key(assignment()),
            automatic(),
            generated_at="2026-07-12",
            required_assignment_count=1,
        )
        markdown = render_explanation_human_evaluation_markdown(report)

        self.assertIn("# 설명 품질 블라인드 사람 평가", markdown)
        self.assertIn("After non-tie 선호 승률", markdown)
        self.assertIn("pairwise exact agreement", markdown)
        self.assertIn("커버리지 기준을 충족하기 전", markdown)


if __name__ == "__main__":
    unittest.main()
