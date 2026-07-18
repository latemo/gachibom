import csv
import io
import json
import unittest
from datetime import date

from src.explanation_evaluation import (
    aggregate_ab_results,
    build_explanation_evaluation_report,
    evaluate_mode_accuracy,
    evaluate_response,
    evaluate_score_trace,
    evaluate_term_coverage,
    find_safety_violations,
    find_unsupported_place_mentions,
    render_evaluations_csv,
    render_explanation_evaluation_json,
    render_explanation_evaluation_markdown,
)


TRACE = {
    "base_total": 80,
    "bonuses": [{"id": "fit", "label": "조건 일치", "delta": 5}],
    "deductions": [{"id": "old", "label": "정보 확인일", "delta": -1}],
    "caps": [{"id": "verified", "label": "상한 적용", "before": 104, "after": 100}],
    "final_total": 84,
}


def case(case_id="score-runtime"):
    return {
        "id": case_id,
        "question_type": "score_explanation",
        "question": "이 점수는 어떻게 계산됐나요?",
        "expected_mode": "runtime",
        "calculation_trace": TRACE,
        "expected_evidence": ["도보 부담이 낮은 편", ["장애인 화장실", "접근 가능한 화장실"]],
        "expected_user_conditions": ["긴 걷기 어려움", "휠체어 접근"],
        "known_place_names": ["제주문학관", "동문재래시장"],
        "supported_place_names": ["제주문학관"],
    }


def record(variant, answer, case_id="score-runtime"):
    return {
        "case_id": case_id,
        "variant": variant,
        "status": "success",
        "model": "fake-model",
        "response": {"answer": answer, "followups": [], "handoff_checklist": []},
        "latency_ms": 12,
        "attempts": 1,
    }


class ExplanationEvaluationTests(unittest.TestCase):
    def test_score_trace_matches_signed_deduction_and_all_distinct_values(self):
        result = evaluate_score_trace(
            "기본 점수 80점에 조건 일치 보너스 5점, 정보 확인일로 1점 감점했습니다. "
            "상한은 104점에서 100점으로 적용했고 최종 점수는 84점입니다.",
            TRACE,
        )

        self.assertEqual(result["value"], 1.0)
        self.assertEqual(result["unsupported_numbers"], [])
        self.assertIn(-1, result["matched_numbers"])

    def test_score_trace_reports_missing_and_wrong_numeric_claims(self):
        result = evaluate_score_trace("기본 점수는 81점이고 최종 점수는 84점입니다.", TRACE)

        self.assertEqual(result["value"], 0.1667)
        self.assertEqual(result["unsupported_numbers"], [81])
        self.assertEqual(len(result["missing_numbers"]), 5)

    def test_score_trace_can_be_not_applicable(self):
        result = evaluate_score_trace("방문 전에 문의하세요.", TRACE, applicable=False)

        self.assertFalse(result["applicable"])
        self.assertIsNone(result["value"])

    def test_term_coverage_supports_paraphrase_and_alias_groups(self):
        result = evaluate_term_coverage(
            "도보 부담이 낮고 접근 가능한 화장실이 확인됐습니다.",
            ["도보 부담이 낮은 편", ["장애인 화장실", "접근 가능한 화장실"], "주차 가능"],
        )

        self.assertEqual(result["value"], 0.6667)
        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(result["missing"], ["주차 가능"])

    def test_mode_accuracy_requires_explicit_correct_mode(self):
        self.assertEqual(evaluate_mode_accuracy("현재 입력으로 실시간 계산한 결과입니다.", "runtime")["value"], 1.0)
        static = evaluate_mode_accuracy("실시간 재계산이 아니라 가장 가까운 사전 계산 시나리오입니다.", "static")
        self.assertEqual(static["detected"], "static")
        self.assertEqual(static["value"], 1.0)
        self.assertEqual(
            evaluate_mode_accuracy("실시간 개인별 재계산 결과가 아닌 사전 계산 결과입니다.", "static")["value"],
            1.0,
        )
        self.assertEqual(
            evaluate_mode_accuracy("사전 계산 결과이며 실시간 재계산을 원하면 다시 요청해 주세요.", "static")["value"],
            1.0,
        )
        self.assertEqual(evaluate_mode_accuracy("추천 결과입니다.", "runtime")["value"], 0.0)

    def test_safety_detector_ignores_negated_disclaimer(self):
        violations = find_safety_violations("누구나 갈 수 있습니다. 문제없이 이동하고 이용을 보장합니다.")
        safe = find_safety_violations("누구나 갈 수 있다고 보장할 수 없으며 100% 가능하지 않습니다.")

        self.assertEqual({item["id"] for item in violations}, {"universal_access", "problem_free_mobility", "guarantee"})
        self.assertEqual(safe, [])

    def test_unsupported_place_mentions_only_flags_known_but_unbacked_names(self):
        unsupported = find_unsupported_place_mentions(
            "제주문학관 대신 동문재래시장도 좋습니다.",
            ["제주문학관", "동문재래시장", "성산일출봉"],
            ["제주문학관"],
        )

        self.assertEqual(unsupported, ["동문재래시장"])

    def test_evaluate_response_returns_scalar_metrics_and_evidence(self):
        evaluation = evaluate_response(
            case(),
            record(
                "after",
                "긴 걷기가 어려워 도보 부담이 낮은 제주문학관을 골랐고 휠체어 접근을 확인했습니다. "
                "현재 입력으로 실시간 계산했으며 최종 점수는 84점입니다.",
            ),
        )

        self.assertEqual(evaluation["variant"], "after")
        self.assertIsNone(evaluation["metrics"]["mode_accuracy"])
        self.assertEqual(evaluation["metrics"]["user_condition_coverage"], 1.0)
        self.assertEqual(evaluation["metrics"]["safety_violation_rate"], 0.0)
        self.assertEqual(evaluation["checks"]["known_places"]["unsupported_mentions"], [])

    def test_mode_metric_only_applies_to_mode_questions(self):
        non_mode_case = case("reason-runtime")
        non_mode_case["question_type"] = "recommendation_reason"
        non_mode_case["question"] = "왜 추천됐나요?"

        evaluation = evaluate_response(non_mode_case, record("after", "조건에 맞는 추천입니다.", case_id="reason-runtime"))

        self.assertIsNone(evaluation["metrics"]["mode_accuracy"])
        self.assertFalse(evaluation["checks"]["mode"]["applicable"])

    def test_failed_response_is_excluded_from_quality_metrics(self):
        failed = record("after", "LLM 도움말 답변 생성에 실패했습니다: JSONDecodeError")
        failed["status"] = "error"

        evaluation = evaluate_response(case(), failed)

        self.assertFalse(evaluation["has_response"])
        self.assertTrue(all(value is None for value in evaluation["metrics"].values()))
        self.assertEqual(evaluation["checks"]["evaluation_status"], "skipped_unsuccessful_response")

    def test_aggregate_ab_results_uses_metric_direction_for_improvement(self):
        mode_case = case()
        mode_case["question_type"] = "mode_distinction"
        before = evaluate_response(
            mode_case,
            record("before", "동문재래시장은 누구나 갈 수 있습니다. 최종 점수는 90점입니다."),
        )
        after = evaluate_response(
            mode_case,
            record(
                "after",
                "긴 걷기가 어려운 조건과 휠체어 접근을 반영했습니다. 도보 부담이 낮은 편이고 "
                "장애인 화장실을 확인했습니다. 현재 입력으로 실시간 계산했습니다. "
                "기본 80점, 보너스 5점, 1점 감점, 104점에서 100점 상한 후 최종 84점입니다.",
            ),
        )

        summary = aggregate_ab_results([before, after])

        self.assertEqual(summary["variants"]["before"]["record_count"], 1)
        self.assertEqual(summary["variants"]["after"]["metrics"]["mode_accuracy"], 1.0)
        self.assertEqual(summary["variants"]["after"]["mean_latency_ms"], 12.0)
        self.assertEqual(summary["variants"]["after"]["p95_latency_ms"], 12.0)
        self.assertEqual(summary["variants"]["after"]["mean_attempts"], 1.0)
        self.assertEqual(summary["deltas"]["safety_violation_rate"]["improvement"], 1.0)
        self.assertEqual(summary["deltas"]["unsupported_place_mention_rate"]["improvement"], 1.0)

    def test_report_and_renderers_are_pure_json_csv_markdown_outputs(self):
        cases = [case()]
        records = [
            record("before", "일반적인 추천 결과입니다."),
            record(
                "after",
                "긴 걷기가 어려운 조건과 휠체어 접근을 반영한 도보 부담이 낮은 제주문학관입니다. "
                "장애인 화장실 근거가 있고 현재 입력으로 실시간 계산했습니다. 최종 84점입니다.",
            ),
        ]
        report = build_explanation_evaluation_report(cases, records, generated_at=date(2026, 7, 12))

        json_text = render_explanation_evaluation_json(report)
        csv_text = render_evaluations_csv(report)
        markdown = render_explanation_evaluation_markdown(report)

        self.assertEqual(json.loads(json_text)["generated_at"], "2026-07-12")
        self.assertEqual(report["methodology"]["human_review_status"], "pending")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["variant"], "after")
        self.assertIn("# 설명 품질 Before/After 평가", markdown)
        self.assertIn("점수 계산 숫자 정확성", markdown)

    def test_unknown_case_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown evaluation case_id"):
            build_explanation_evaluation_report([case()], [record("after", "답변", case_id="missing")])


if __name__ == "__main__":
    unittest.main()
