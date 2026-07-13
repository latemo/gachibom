import csv
import io
import json
import unittest
from copy import deepcopy

from src.explanation_blind_review import (
    BLIND_REVIEW_CSV_FIELDS,
    BlindReviewInputError,
    build_blind_review_packet,
    compute_review_row_fingerprint,
    compute_source_fingerprint,
    render_blind_review_csv,
    render_deblind_key_json,
)


def make_report(case_count=6):
    evaluations = []
    records = []
    for index in range(case_count):
        case_id = f"case-{index:02d}"
        question_type = "pre_visit_check" if index == 0 else "recommendation_reason"
        question = f"질문 {index}"
        for variant in ("before", "after"):
            answer = f"{case_id} {variant} 응답"
            evaluations.append(
                {
                    "case_id": case_id,
                    "variant": variant,
                    "question_type": question_type,
                    "question": question,
                    "record_status": "success",
                    "has_response": True,
                    "response_text": answer,
                    "latency_ms": index + 1,
                    "checks": {
                        "score_trace": {
                            "applicable": False,
                            "expected_numbers": [{"path": "final_total", "label": "최종 점수", "value": 90 + index}],
                        },
                        "expected_evidence": {
                            "applicable": True,
                            "matched": [f"근거 {index}"] if variant == "after" else [],
                            "missing": [] if variant == "after" else [f"근거 {index}"],
                        },
                        "user_conditions": {
                            "applicable": True,
                            "matched": ["이동 조건"] if variant == "after" else [],
                            "missing": [] if variant == "after" else ["이동 조건"],
                        },
                        "mode": {"applicable": False, "expected": None},
                    },
                }
            )
            records.append(
                {
                    "case_id": case_id,
                    "variant": variant,
                    "status": "success",
                    "latency_ms": index + 2,
                    "response": {"answer": answer},
                }
            )
    return {
        "schema_version": "1.0",
        "generated_at": "2026-07-12T00:00:00Z",
        "summary": {"volatile": True},
        "evaluations": evaluations,
        "records": records,
    }


def make_cases(case_count=6):
    cases = []
    for index in range(case_count):
        cases.append(
            {
                "id": f"case-{index:02d}",
                "question_type": "pre_visit_check" if index == 0 else "recommendation_reason",
                "question": f"질문 {index}",
                "recommendation_context": {"must_not": "be exposed"},
                "expected": {
                    "mode": "static",
                    "score": {"total": 90 + index, "grade": "A"},
                    "conditions": {"mobility_conditions": ["긴 걷기 어려움"]},
                    "reasons": {"fit": [f"근거 {index}"]},
                    "checks": ["운영 여부 확인"],
                    "limitations": ["현장 상황은 달라질 수 있음"],
                    "sources": [{"url": "https://should-not-be-exposed.example"}],
                },
                "known_place_names": ["노출하지 않을 장소 목록"],
            }
        )
    return cases


class ExplanationBlindReviewTests(unittest.TestCase):
    def test_same_seed_is_fully_reproducible_and_renderable(self):
        report = make_report(8)

        first = build_blind_review_packet(report, seed="stable-seed")
        second = build_blind_review_packet(deepcopy(report), seed="stable-seed")

        self.assertEqual(first, second)
        self.assertEqual(first["source_fingerprint"], compute_source_fingerprint(report))
        csv_rows = list(csv.DictReader(io.StringIO(render_blind_review_csv(first))))
        self.assertEqual(len(csv_rows), 8)
        self.assertEqual(tuple(csv_rows[0]), BLIND_REVIEW_CSV_FIELDS)
        self.assertEqual(
            csv_rows[0]["immutable_fingerprint"], compute_review_row_fingerprint(csv_rows[0])
        )
        self.assertEqual(
            csv_rows[0]["immutable_fingerprint"],
            first["deblind_key"]["assignments"][0]["immutable_fingerprint"],
        )
        rendered_key = json.loads(render_deblind_key_json(first))
        self.assertEqual(rendered_key, first["deblind_key"])

    def test_different_seeds_change_case_order_and_assignments(self):
        report = make_report(12)

        first = build_blind_review_packet(report, seed="seed-alpha")
        second = build_blind_review_packet(report, seed="seed-beta")
        first_mapping = [
            (item["blind_id"], item["case_id"], item["answer_a_variant"])
            for item in first["deblind_key"]["assignments"]
        ]
        second_mapping = [
            (item["blind_id"], item["case_id"], item["answer_a_variant"])
            for item in second["deblind_key"]["assignments"]
        ]

        self.assertNotEqual(first_mapping, second_mapping)

    def test_thirty_cases_are_balanced_and_blind_rows_hide_variants(self):
        packet = build_blind_review_packet(make_report(30), seed="balanced-seed")

        self.assertEqual(packet["deblind_key"]["answer_a_counts"], {"before": 15, "after": 15})
        self.assertEqual(
            [row["blind_id"] for row in packet["review_rows"]],
            [f"BR-{index:03d}" for index in range(1, 31)],
        )
        for row in packet["review_rows"]:
            self.assertNotIn("case_id", row)
            self.assertNotIn("variant", row)
            self.assertEqual(row["reviewer_id"], "")
            self.assertEqual(row["review_status"], "")
            self.assertEqual(row["notes"], "")
            self.assertEqual(row["preference"], "")

        counts = packet["deblind_key"]["answer_a_counts"]
        self.assertLessEqual(abs(counts["before"] - counts["after"]), 1)

    def test_previsit_fields_are_blank_only_when_applicable(self):
        packet = build_blind_review_packet(make_report(4), seed="previsit")
        previsit = next(row for row in packet["review_rows"] if row["question_type"] == "pre_visit_check")
        other = next(row for row in packet["review_rows"] if row["question_type"] != "pre_visit_check")

        self.assertEqual(previsit["previsit_applicable"], "yes")
        self.assertEqual(previsit["answer_a_previsit_clarity_yes_no"], "")
        self.assertEqual(previsit["answer_b_previsit_clarity_yes_no"], "")
        self.assertEqual(other["previsit_applicable"], "no")
        self.assertEqual(other["answer_a_previsit_clarity_yes_no"], "n/a")
        self.assertEqual(other["answer_b_previsit_clarity_yes_no"], "n/a")

    def test_optional_cases_join_only_whitelists_expected_reference_facts(self):
        packet = build_blind_review_packet(
            make_report(3), seed="with-cases", cases={"schema_version": "1.0", "cases": make_cases(3)}
        )
        row = next(row for row in packet["review_rows"] if row["question"] == "질문 1")
        facts = json.loads(row["reference_facts"])

        self.assertEqual(
            set(facts), {"mode", "score", "conditions", "reasons", "checks", "limitations"}
        )
        self.assertEqual(facts["mode"], "static")
        self.assertEqual(facts["score"]["total"], 91)
        self.assertEqual(facts["conditions"]["mobility_conditions"], ["긴 걷기 어려움"])
        self.assertNotIn("recommendation_context", row["reference_facts"])
        self.assertNotIn("sources", row["reference_facts"])
        self.assertNotIn("known_place_names", row["reference_facts"])

    def test_source_fingerprint_ignores_run_metadata_but_tracks_review_text(self):
        report = make_report(2)
        rerendered = deepcopy(report)
        rerendered["generated_at"] = "2030-01-01T00:00:00Z"
        rerendered["summary"] = {"different": "metrics"}
        rerendered["evaluations"][0]["latency_ms"] = 999999
        rerendered["records"][0]["latency_ms"] = 999999

        self.assertEqual(compute_source_fingerprint(report), compute_source_fingerprint(rerendered))

        changed = deepcopy(report)
        changed["evaluations"][0]["response_text"] = "수정된 응답"
        changed["records"][0]["response"]["answer"] = "수정된 응답"
        self.assertNotEqual(compute_source_fingerprint(report), compute_source_fingerprint(changed))

    def test_seed_is_not_exposed_in_packet_or_key(self):
        seed = "super-secret-randomization-seed"
        packet = build_blind_review_packet(make_report(4), seed=seed)

        self.assertNotIn(seed, json.dumps(packet, ensure_ascii=False))
        self.assertNotIn("seed", packet["deblind_key"])

    def test_immutable_fingerprint_detects_reviewer_visible_content_change(self):
        packet = build_blind_review_packet(make_report(4), seed="integrity")
        row = packet["review_rows"][0]
        assignment = packet["deblind_key"]["assignments"][0]

        self.assertEqual(assignment["immutable_fingerprint"], compute_review_row_fingerprint(row))
        self.assertEqual(row["immutable_fingerprint"], assignment["immutable_fingerprint"])
        changed = deepcopy(row)
        changed["answer_a"] += "!"
        self.assertNotEqual(assignment["immutable_fingerprint"], compute_review_row_fingerprint(changed))

        reformatted = deepcopy(row)
        reformatted["reference_facts"] = json.dumps(
            json.loads(row["reference_facts"]), ensure_ascii=False, indent=2
        )
        self.assertEqual(assignment["immutable_fingerprint"], compute_review_row_fingerprint(reformatted))

    def test_rejects_incomplete_duplicate_failed_and_mismatched_inputs(self):
        with self.subTest("missing report list"):
            with self.assertRaisesRegex(BlindReviewInputError, "records"):
                build_blind_review_packet({"evaluations": []}, seed="x")

        with self.subTest("incomplete pair"):
            incomplete = make_report(2)
            incomplete["evaluations"] = [
                row
                for row in incomplete["evaluations"]
                if not (row["case_id"] == "case-00" and row["variant"] == "after")
            ]
            incomplete["records"] = [
                row
                for row in incomplete["records"]
                if not (row["case_id"] == "case-00" and row["variant"] == "after")
            ]
            with self.assertRaisesRegex(BlindReviewInputError, "missing variants"):
                build_blind_review_packet(incomplete, seed="x")

        with self.subTest("duplicate"):
            duplicate = make_report(2)
            duplicate["records"].append(deepcopy(duplicate["records"][0]))
            with self.assertRaisesRegex(BlindReviewInputError, "duplicate records pair"):
                build_blind_review_packet(duplicate, seed="x")

        with self.subTest("failed"):
            failed = make_report(2)
            failed["records"][0]["status"] = "error"
            with self.assertRaisesRegex(BlindReviewInputError, "not successful"):
                build_blind_review_packet(failed, seed="x")

        with self.subTest("response mismatch"):
            mismatched = make_report(2)
            mismatched["records"][0]["response"]["answer"] = "다른 응답"
            with self.assertRaisesRegex(BlindReviewInputError, "mismatched"):
                build_blind_review_packet(mismatched, seed="x")

        with self.subTest("missing source case"):
            with self.assertRaisesRegex(BlindReviewInputError, "missing report case"):
                build_blind_review_packet(make_report(2), seed="x", cases=make_cases(1))


if __name__ == "__main__":
    unittest.main()
