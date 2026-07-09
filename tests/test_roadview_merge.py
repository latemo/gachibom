import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.roadview_merge import (
    apply_manual_conflict_resolutions,
    apply_manual_match_resolutions,
    apply_safe_roadview_updates,
    build_merge_review_report,
)


ROOT = Path(__file__).resolve().parents[1]


def card(
    card_id,
    name,
    *,
    region="제주시",
    category="indoor",
    toilet="unknown",
    parking="yes",
    rest_area="partial",
    rental="unknown",
):
    return {
        "id": card_id,
        "name": name,
        "region": region,
        "category": category,
        "verification": {"status": "partial"},
        "accessibility": {
            "accessible_toilet": {"state": toilet, "note": f"toilet {toilet}", "source_ref": "test"},
            "parking": {"state": parking, "note": f"parking {parking}", "source_ref": "test"},
            "rest_area": {"state": rest_area, "note": f"rest {rest_area}", "source_ref": "test"},
            "rental_or_assistance": {"state": rental, "note": f"rental {rental}", "source_ref": "test"},
        },
    }


def full_card(
    card_id,
    name,
    *,
    parking="partial",
    rest_area="unknown",
    missing_fields=None,
):
    return {
        "id": card_id,
        "name": name,
        "region": "제주시",
        "category": "indoor",
        "summary": f"{name} 접근성 카드",
        "recommended_for": ["wheelchair_user"],
        "avoid_for": [],
        "accessibility": {
            "wheelchair_access": {"state": "partial", "note": "동선 확인 필요", "source_ref": "test"},
            "accessible_toilet": {"state": "unknown", "note": "확인 필요", "source_ref": None},
            "parking": {"state": parking, "note": f"parking {parking}", "source_ref": "test"},
            "slope_or_stairs": {"state": "needs_check", "note": "확인 필요", "source_ref": None},
            "rest_area": {"state": rest_area, "note": f"rest {rest_area}", "source_ref": "test"},
            "rental_or_assistance": {"state": "unknown", "note": "확인 필요", "source_ref": None},
            "surface_condition": {"state": "needs_check", "note": "확인 필요", "source_ref": None},
            "crowd_level": {"state": "unknown", "note": "확인 필요", "source_ref": None},
        },
        "effort": {
            "walking_level": "unknown",
            "recommended_duration_minutes": None,
            "outdoor_exposure": "unknown",
            "weather_sensitivity": "unknown",
        },
        "sources": [{"title": "테스트 출처", "url": "https://example.com", "type": "unknown"}],
        "verification": {
            "status": "partial",
            "checked_at": "2026-07-07",
            "checked_by": "test",
            "missing_fields": missing_fields or ["parking", "rest_area"],
        },
        "status": "active",
        "safety_notes": [],
        "operator_notes": "initial",
    }


class RoadviewMergeTests(unittest.TestCase):
    def test_build_merge_review_report_classifies_updates_new_and_manual(self):
        existing = [
            card("jeju_indoor_literature_022", "제주문학관", toilet="unknown", rental="unknown"),
            card("jeju_sea_sample_001", "협재해수욕장", toilet="no"),
            card("jeju_indoor_annex_001", "제주문학관 별관"),
        ]
        drafts = [
            card("jeju_roadview_place_001", "제주문학관", toilet="yes", rental="yes"),
            card("jeju_roadview_place_002", "새로운관광지", region="서귀포시", category="other"),
            card("jeju_roadview_place_003", "제주문학관 별관 안내소"),
            card("jeju_roadview_place_004", "협재해수욕장", category="sea", toilet="yes"),
        ]

        report = build_merge_review_report(existing, drafts, generated_at=date(2026, 7, 7))

        self.assertEqual(report["summary"]["existing_count"], 3)
        self.assertEqual(report["summary"]["draft_count"], 4)
        self.assertEqual(report["summary"]["matched_existing"], 2)
        self.assertEqual(report["summary"]["new_candidate"], 1)
        self.assertEqual(report["summary"]["needs_manual_review"], 2)
        self.assertEqual(report["summary"]["field_updates_available"], 1)
        self.assertEqual(report["field_updates_available"][0]["existing"]["id"], "jeju_indoor_literature_022")
        self.assertEqual(report["new_candidate"][0]["draft"]["name"], "새로운관광지")
        self.assertEqual(report["needs_manual_review"][0]["review_type"], "uncertain_match")
        self.assertEqual(report["needs_manual_review"][1]["review_type"], "field_conflict")

        schema = json.loads((ROOT / "data" / "schemas" / "roadview_merge_report.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_review_roadview_merge_cli_writes_report(self):
        existing = [card("jeju_indoor_literature_022", "제주문학관", toilet="unknown", rental="unknown")]
        drafts = [card("jeju_roadview_place_001", "제주문학관", toilet="yes", rental="yes")]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            existing_path = temp_path / "existing.json"
            draft_path = temp_path / "draft.json"
            output_path = temp_path / "report.json"
            existing_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
            draft_path.write_text(json.dumps(drafts, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "review_roadview_merge.py"),
                    "--existing",
                    str(existing_path),
                    "--draft",
                    str(draft_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-07",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("field_updates_available:1", result.stdout)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["matched_existing"], 1)

    def test_apply_safe_roadview_updates_applies_yes_and_queues_other_items(self):
        existing = [full_card("jeju_indoor_literature_022", "제주문학관")]
        report = {
            "generated_at": "2026-07-07",
            "summary": {
                "existing_count": 1,
                "draft_count": 2,
                "matched_existing": 1,
                "new_candidate": 1,
                "needs_manual_review": 0,
                "field_updates_available": 1,
            },
            "matched_existing": [],
            "new_candidate": [
                {
                    "draft": {
                        "id": "jeju_roadview_place_002",
                        "name": "새로운관광지",
                        "region": "제주시",
                        "category": "other",
                        "verification_status": "partial",
                    },
                    "recommended_action": "review_before_adding",
                    "reason": "신규 후보",
                }
            ],
            "needs_manual_review": [],
            "field_updates_available": [
                {
                    "existing": {
                        "id": "jeju_indoor_literature_022",
                        "name": "제주문학관",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "partial",
                    },
                    "draft": {
                        "id": "jeju_roadview_place_001",
                        "name": "제주문학관",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "partial",
                    },
                    "match_confidence": 1,
                    "match_reasons": ["name_exact"],
                    "field_conflicts": [],
                    "field_updates": [
                        {
                            "field": "parking",
                            "existing_state": "partial",
                            "existing_note": "parking partial",
                            "draft_state": "yes",
                            "draft_note": "장애인 주차장 보유 수: 1개",
                            "draft_source_ref": "jeju_roadview_facility_status",
                            "recommended_action": "review_and_update_existing_card",
                        },
                        {
                            "field": "rest_area",
                            "existing_state": "unknown",
                            "existing_note": "rest unknown",
                            "draft_state": "no",
                            "draft_note": "휴게실 보유 여부: N",
                            "draft_source_ref": "jeju_roadview_facility_status",
                            "recommended_action": "review_and_update_existing_card",
                        },
                    ],
                }
            ],
        }

        result = apply_safe_roadview_updates(existing, report, applied_at=date(2026, 7, 7))
        merged_card = result["cards"][0]

        self.assertEqual(merged_card["accessibility"]["parking"]["state"], "yes")
        self.assertEqual(merged_card["accessibility"]["rest_area"]["state"], "unknown")
        self.assertNotIn("parking", merged_card["verification"]["missing_fields"])
        self.assertIn("rest_area", merged_card["verification"]["missing_fields"])
        self.assertEqual(result["apply_report"]["summary"]["safe_field_updates_applied"], 1)
        self.assertEqual(result["apply_report"]["summary"]["skipped_field_updates"], 1)
        self.assertEqual(result["manual_review_queue"]["summary"]["by_review_type"]["new_candidate"], 1)
        self.assertEqual(result["manual_review_queue"]["summary"]["by_review_type"]["auto_skipped_field_update"], 1)

        schema = json.loads((ROOT / "data" / "schemas" / "accessibility_place_card.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(merged_card)), [])
        apply_report_schema = json.loads((ROOT / "data" / "schemas" / "roadview_apply_report.schema.json").read_text(encoding="utf-8"))
        review_queue_schema = json.loads((ROOT / "data" / "schemas" / "roadview_manual_review_queue.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(apply_report_schema).iter_errors(result["apply_report"])), [])
        self.assertEqual(list(Draft202012Validator(review_queue_schema).iter_errors(result["manual_review_queue"])), [])

    def test_apply_roadview_safe_updates_cli_writes_outputs(self):
        existing = [full_card("jeju_indoor_literature_022", "제주문학관")]
        draft = [card("jeju_roadview_place_001", "제주문학관", parking="yes", rest_area="no")]
        report = build_merge_review_report(existing, draft, generated_at=date(2026, 7, 7))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            existing_path = temp_path / "existing.json"
            report_path = temp_path / "report.json"
            output_path = temp_path / "merged.json"
            manual_review_path = temp_path / "manual_review.json"
            apply_report_path = temp_path / "apply_report.json"
            existing_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "apply_roadview_safe_updates.py"),
                    "--existing",
                    str(existing_path),
                    "--report",
                    str(report_path),
                    "--output",
                    str(output_path),
                    "--manual-review-output",
                    str(manual_review_path),
                    "--apply-report-output",
                    str(apply_report_path),
                    "--applied-at",
                    "2026-07-07",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("safe_field_updates_applied:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))[0]["accessibility"]["parking"]["state"], "yes")
            self.assertEqual(json.loads(manual_review_path.read_text(encoding="utf-8"))["summary"]["total"], 1)
            self.assertEqual(json.loads(apply_report_path.read_text(encoding="utf-8"))["summary"]["cards_updated"], 1)

    def test_apply_manual_conflict_resolutions_keeps_existing_and_closes_items(self):
        existing = [full_card("jeju_indoor_literature_022", "제주문학관")]
        existing[0]["accessibility"]["rental_or_assistance"] = {
            "state": "yes",
            "note": "휠체어 1대 안내데스크 대여 가능",
            "source_ref": "visitkorea",
        }
        queue = {
            "generated_at": "2026-07-07",
            "source_report_generated_at": "2026-07-07",
            "summary": {"total": 1, "by_review_type": {"field_conflict": 1}, "by_priority": {"high": 1}},
            "items": [
                {
                    "review_type": "field_conflict",
                    "priority": "high",
                    "reason": "충돌",
                    "existing": {
                        "id": "jeju_indoor_literature_022",
                        "name": "제주문학관",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "verified",
                    },
                    "draft": {
                        "id": "jeju_roadview_place_001",
                        "name": "제주문학관",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "partial",
                    },
                    "match_confidence": 1,
                    "match_reasons": ["name_exact"],
                    "field_conflicts": [
                        {
                            "field": "rental_or_assistance",
                            "existing_state": "yes",
                            "existing_note": "휠체어 1대 안내데스크 대여 가능",
                            "draft_state": "no",
                            "draft_note": "휠체어 대여 가능 여부: N",
                            "draft_source_ref": "jeju_roadview_facility_status",
                            "recommended_action": "review_and_update_existing_card",
                        }
                    ],
                }
            ],
        }
        resolutions = {
            "generated_at": "2026-07-07",
            "resolutions": [
                {
                    "existing_id": "jeju_indoor_literature_022",
                    "existing_name": "제주문학관",
                    "draft_id": "jeju_roadview_place_001",
                    "field": "rental_or_assistance",
                    "decision": "keep_existing",
                    "kept_state": "yes",
                    "rejected_state": "no",
                    "reason": "상세 편의정보가 대여 가능으로 확인됨",
                    "safety_note": "대여 수량은 방문 전 확인 필요",
                }
            ],
        }

        result = apply_manual_conflict_resolutions(existing, queue, resolutions, applied_at=date(2026, 7, 7))
        card = result["cards"][0]

        self.assertEqual(card["accessibility"]["rental_or_assistance"]["state"], "yes")
        self.assertEqual(result["open_manual_review_queue"]["summary"]["total"], 0)
        self.assertEqual(result["resolution_apply_report"]["summary"]["resolutions_applied"], 1)
        self.assertIn("roadview_conflict_resolution", card["operator_notes"])
        self.assertIn("대여 수량은 방문 전 확인 필요", card["safety_notes"])

    def test_apply_roadview_conflict_resolutions_cli_writes_outputs(self):
        existing = [full_card("jeju_indoor_literature_022", "제주문학관")]
        queue = {
            "generated_at": "2026-07-07",
            "source_report_generated_at": "2026-07-07",
            "summary": {"total": 1, "by_review_type": {"field_conflict": 1}, "by_priority": {"high": 1}},
            "items": [
                {
                    "review_type": "field_conflict",
                    "priority": "high",
                    "reason": "충돌",
                    "existing": {
                        "id": "jeju_indoor_literature_022",
                        "name": "제주문학관",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "verified",
                    },
                    "draft": {
                        "id": "jeju_roadview_place_001",
                        "name": "제주문학관",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "partial",
                    },
                    "match_confidence": 1,
                    "match_reasons": ["name_exact"],
                    "field_conflicts": [
                        {
                            "field": "rest_area",
                            "existing_state": "yes",
                            "existing_note": "휴식 가능",
                            "draft_state": "no",
                            "draft_note": "휴게실 보유 여부: N",
                            "draft_source_ref": "jeju_roadview_facility_status",
                            "recommended_action": "review_and_update_existing_card",
                        }
                    ],
                }
            ],
        }
        resolutions = {
            "generated_at": "2026-07-07",
            "resolutions": [
                {
                    "existing_id": "jeju_indoor_literature_022",
                    "existing_name": "제주문학관",
                    "draft_id": "jeju_roadview_place_001",
                    "field": "rest_area",
                    "decision": "keep_existing",
                    "kept_state": "yes",
                    "rejected_state": "no",
                    "reason": "rest_area와 휴게실은 의미 범위가 다름",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            existing_path = temp_path / "existing.json"
            queue_path = temp_path / "queue.json"
            resolutions_path = temp_path / "resolutions.json"
            output_path = temp_path / "cards.json"
            open_queue_path = temp_path / "open_queue.json"
            apply_report_path = temp_path / "apply_report.json"
            existing_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
            queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
            resolutions_path.write_text(json.dumps(resolutions, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "apply_roadview_conflict_resolutions.py"),
                    "--existing",
                    str(existing_path),
                    "--manual-review",
                    str(queue_path),
                    "--resolutions",
                    str(resolutions_path),
                    "--output",
                    str(output_path),
                    "--open-manual-review-output",
                    str(open_queue_path),
                    "--apply-report-output",
                    str(apply_report_path),
                    "--applied-at",
                    "2026-07-07",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("resolutions_applied:1", result.stdout)
            self.assertEqual(json.loads(open_queue_path.read_text(encoding="utf-8"))["summary"]["total"], 0)
            self.assertEqual(json.loads(apply_report_path.read_text(encoding="utf-8"))["summary"]["resolved_field_conflict_items"], 1)

    def test_apply_manual_match_resolutions_closes_uncertain_match(self):
        existing = [full_card("jeju_indoor_starlight_025", "별빛누리공원")]
        queue = {
            "generated_at": "2026-07-08",
            "source_report_generated_at": "2026-07-07",
            "summary": {"total": 1, "by_review_type": {"uncertain_match": 1}, "by_priority": {"medium": 1}},
            "items": [
                {
                    "review_type": "uncertain_match",
                    "priority": "medium",
                    "reason": "장소명이 부분 일치",
                    "existing": {
                        "id": "jeju_indoor_starlight_025",
                        "name": "별빛누리공원",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "partial",
                    },
                    "draft": {
                        "id": "jeju_roadview_place_086",
                        "name": "제주별빛누리공원",
                        "region": "제주시",
                        "category": "rest_area",
                        "verification_status": "partial",
                    },
                    "match_confidence": 0.73,
                    "match_reasons": ["name_contains"],
                    "field_conflicts": [],
                }
            ],
        }
        resolutions = {
            "generated_at": "2026-07-08",
            "resolutions": [
                {
                    "existing_id": "jeju_indoor_starlight_025",
                    "existing_name": "별빛누리공원",
                    "draft_id": "jeju_roadview_place_086",
                    "draft_name": "제주별빛누리공원",
                    "decision": "confirmed_same_place",
                    "reason": "공식명 접두어 차이로 판단",
                    "safety_note": "야간 프로그램 운영 여부 확인 필요",
                }
            ],
        }

        result = apply_manual_match_resolutions(existing, queue, resolutions, applied_at=date(2026, 7, 8))
        card = result["cards"][0]

        self.assertEqual(result["open_manual_review_queue"]["summary"]["total"], 0)
        self.assertEqual(result["match_resolution_apply_report"]["summary"]["resolved_uncertain_match_items"], 1)
        self.assertIn("roadview_match_resolution", card["operator_notes"])
        self.assertIn("야간 프로그램 운영 여부 확인 필요", card["safety_notes"])

    def test_apply_roadview_match_resolutions_cli_writes_outputs(self):
        existing = [full_card("jeju_indoor_starlight_025", "별빛누리공원")]
        queue = {
            "generated_at": "2026-07-08",
            "source_report_generated_at": "2026-07-07",
            "summary": {"total": 1, "by_review_type": {"uncertain_match": 1}, "by_priority": {"medium": 1}},
            "items": [
                {
                    "review_type": "uncertain_match",
                    "priority": "medium",
                    "reason": "장소명이 부분 일치",
                    "existing": {
                        "id": "jeju_indoor_starlight_025",
                        "name": "별빛누리공원",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "partial",
                    },
                    "draft": {
                        "id": "jeju_roadview_place_086",
                        "name": "제주별빛누리공원",
                        "region": "제주시",
                        "category": "rest_area",
                        "verification_status": "partial",
                    },
                    "match_confidence": 0.73,
                    "match_reasons": ["name_contains"],
                    "field_conflicts": [],
                }
            ],
        }
        resolutions = {
            "generated_at": "2026-07-08",
            "resolutions": [
                {
                    "existing_id": "jeju_indoor_starlight_025",
                    "existing_name": "별빛누리공원",
                    "draft_id": "jeju_roadview_place_086",
                    "draft_name": "제주별빛누리공원",
                    "decision": "confirmed_same_place",
                    "reason": "공식명 접두어 차이로 판단",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            existing_path = temp_path / "existing.json"
            queue_path = temp_path / "queue.json"
            resolutions_path = temp_path / "resolutions.json"
            output_path = temp_path / "cards.json"
            open_queue_path = temp_path / "open_queue.json"
            apply_report_path = temp_path / "apply_report.json"
            existing_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
            queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
            resolutions_path.write_text(json.dumps(resolutions, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "apply_roadview_match_resolutions.py"),
                    "--existing",
                    str(existing_path),
                    "--manual-review",
                    str(queue_path),
                    "--resolutions",
                    str(resolutions_path),
                    "--output",
                    str(output_path),
                    "--open-manual-review-output",
                    str(open_queue_path),
                    "--apply-report-output",
                    str(apply_report_path),
                    "--applied-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("resolved_uncertain_match_items:1", result.stdout)
            self.assertEqual(json.loads(open_queue_path.read_text(encoding="utf-8"))["summary"]["total"], 0)
            self.assertEqual(json.loads(apply_report_path.read_text(encoding="utf-8"))["summary"]["resolutions_applied"], 1)


if __name__ == "__main__":
    unittest.main()
