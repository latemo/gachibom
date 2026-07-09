import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.roadview_new_candidates import (
    build_category_refinement_review,
    build_crowd_policy_review,
    build_official_source_review,
    build_roadview_image_acquisition_request,
    build_roadview_image_asset_manifest,
    build_roadview_image_receipt_report,
    build_roadview_image_review,
    build_roadview_visual_review_sheet,
    apply_roadview_visual_review_sheet,
    build_service_seed_gate_status,
    export_roadview_image_acquisition_csvs,
    build_service_seed_active_candidates,
    build_service_seed_promotion_readiness,
    build_service_seed_cards,
    build_service_seed_review,
    build_service_seed_work_queue,
    triage_new_candidates,
)


ROOT = Path(__file__).resolve().parents[1]


def draft_card(
    card_id,
    name,
    *,
    category="indoor",
    toilet="yes",
    parking="yes",
    rest_area="yes",
    rental="yes",
):
    return {
        "id": card_id,
        "name": name,
        "region": "제주시",
        "category": category,
        "situation_tags": ["restroom_important"],
        "summary": f"{name} 접근성 초안",
        "recommended_for": ["wheelchair_user", "senior"],
        "avoid_for": ["현장 동선 확인 전 장거리 이동이 어려운 사용자"],
        "accessibility": {
            "wheelchair_access": {"state": "partial", "note": "동선 확인 필요", "source_ref": "roadview"},
            "accessible_toilet": {"state": toilet, "note": f"toilet {toilet}", "source_ref": "roadview"},
            "parking": {"state": parking, "note": f"parking {parking}", "source_ref": "roadview"},
            "slope_or_stairs": {"state": "needs_check", "note": "확인 필요", "source_ref": None},
            "rest_area": {"state": rest_area, "note": f"rest {rest_area}", "source_ref": "roadview"},
            "rental_or_assistance": {"state": rental, "note": f"rental {rental}", "source_ref": "roadview"},
            "surface_condition": {"state": "needs_check", "note": "확인 필요", "source_ref": "roadview_image_metadata"},
            "crowd_level": {"state": "unknown", "note": "확인 필요", "source_ref": None},
        },
        "effort": {
            "walking_level": "unknown",
            "recommended_duration_minutes": None,
            "outdoor_exposure": "unknown",
            "weather_sensitivity": "unknown",
        },
        "sources": [{"title": "roadview", "url": "https://www.data.go.kr/data/15109153/fileData.do", "type": "public_agency"}],
        "verification": {
            "status": "partial",
            "checked_at": "2026-07-08",
            "checked_by": "test",
            "missing_fields": ["slope_or_stairs", "surface_condition", "crowd_level"],
        },
        "status": "active",
        "safety_notes": ["현장 확인 필요"],
        "operator_notes": "test",
    }


def queue_for(*card_ids):
    return {
        "generated_at": "2026-07-08",
        "source_report_generated_at": "2026-07-07",
        "summary": {"total": len(card_ids), "by_review_type": {"new_candidate": len(card_ids)}, "by_priority": {"medium": len(card_ids)}},
        "items": [
            {
                "review_type": "new_candidate",
                "priority": "medium",
                "reason": "신규 후보",
                "draft": {
                    "id": card_id,
                    "name": card_id,
                    "region": "제주시",
                    "category": "indoor",
                    "verification_status": "partial",
                },
                "recommended_action": "review_before_adding",
            }
            for card_id in card_ids
        ],
    }


class RoadviewNewCandidateTests(unittest.TestCase):
    def test_triage_new_candidates_classifies_seed_catalog_and_review(self):
        drafts = [
            draft_card("jeju_roadview_seed_001", "시드후보"),
            draft_card("jeju_roadview_catalog_002", "카탈로그후보", rest_area="no", rental="no"),
            draft_card("jeju_roadview_review_003", "현장검수", toilet="no", parking="no", rest_area="no", rental="no"),
        ]

        report = triage_new_candidates(queue_for(*(card["id"] for card in drafts)), drafts, generated_at=date(2026, 7, 8))

        decisions = {item["draft"]["id"]: item["decision"] for item in report["candidates"]}
        self.assertEqual(decisions["jeju_roadview_seed_001"], "service_seed_candidate")
        self.assertEqual(decisions["jeju_roadview_catalog_002"], "catalog_candidate")
        self.assertEqual(decisions["jeju_roadview_review_003"], "field_review_required")

        schema = json.loads((ROOT / "data" / "schemas" / "roadview_new_candidate_triage.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_build_service_seed_cards_marks_cards_hidden(self):
        drafts = [draft_card("jeju_roadview_seed_001", "시드후보")]
        report = triage_new_candidates(queue_for("jeju_roadview_seed_001"), drafts, generated_at=date(2026, 7, 8))

        seed_cards = build_service_seed_cards(report, drafts)

        self.assertEqual(len(seed_cards), 1)
        self.assertEqual(seed_cards[0]["status"], "hidden")
        self.assertIn("roadview_new_candidate_triage", seed_cards[0]["operator_notes"])
        schema = json.loads((ROOT / "data" / "schemas" / "accessibility_place_card.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(seed_cards[0])), [])

    def test_triage_roadview_new_candidates_cli_writes_outputs(self):
        drafts = [draft_card("jeju_roadview_seed_001", "시드후보")]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            queue_path = temp_path / "queue.json"
            draft_path = temp_path / "draft.json"
            output_path = temp_path / "triage.json"
            seed_path = temp_path / "seed.json"
            queue_path.write_text(json.dumps(queue_for("jeju_roadview_seed_001"), ensure_ascii=False), encoding="utf-8")
            draft_path.write_text(json.dumps(drafts, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "triage_roadview_new_candidates.py"),
                    "--queue",
                    str(queue_path),
                    "--draft",
                    str(draft_path),
                    "--output",
                    str(output_path),
                    "--seed-output",
                    str(seed_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("service_seed_candidate:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total"], 1)
            self.assertEqual(json.loads(seed_path.read_text(encoding="utf-8"))[0]["status"], "hidden")

    def test_build_service_seed_review_blocks_until_detail_review(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
            }
        ]

        report = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))

        self.assertEqual(report["summary"]["total"], 1)
        self.assertEqual(report["summary"]["total_roadview_images"], 1)
        self.assertEqual(report["items"][0]["decision"], "blocked_pending_detail_review")
        self.assertIn("official_detail_source_required", report["items"][0]["blockers"])
        self.assertIn("ready_for_image_review", report["summary"]["by_image_review_status"])

        schema = json.loads((ROOT / "data" / "schemas" / "roadview_service_seed_review.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_review_service_seed_cards_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            seed_path = temp_path / "seed.json"
            metadata_path = temp_path / "metadata.json"
            output_path = temp_path / "review.json"
            seed_path.write_text(json.dumps(seed_cards, ensure_ascii=False), encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "review_service_seed_cards.py"),
                    "--seed-cards",
                    str(seed_path),
                    "--image-metadata",
                    str(metadata_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("total_roadview_images:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total"], 1)

    def test_build_service_seed_work_queue_creates_operational_tasks(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보", category="other")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "시드후보", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))

        queue = build_service_seed_work_queue(review, generated_at=date(2026, 7, 8))

        self.assertEqual(queue["summary"]["by_task_type"]["official_source_review"], 1)
        self.assertEqual(queue["summary"]["by_task_type"]["roadview_image_review"], 1)
        self.assertEqual(queue["summary"]["by_task_type"]["crowd_policy_review"], 1)
        self.assertEqual(queue["summary"]["by_task_type"]["category_refinement"], 1)
        self.assertEqual(queue["summary"]["by_status"]["open"], 4)
        schema = json.loads((ROOT / "data" / "schemas" / "roadview_service_seed_work_queue.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(queue)), [])

    def test_build_service_seed_work_queue_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "시드후보", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            review_path = temp_path / "review.json"
            output_path = temp_path / "work_queue.json"
            review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_service_seed_work_queue.py"),
                    "--review",
                    str(review_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("open:3", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total"], 3)

    def test_build_official_source_review_creates_source_verification_items(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "시드후보", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))

        source_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))

        self.assertEqual(source_review["summary"]["total"], 1)
        self.assertEqual(source_review["summary"]["by_status"]["open"], 1)
        self.assertEqual(source_review["summary"]["by_review_decision"]["pending_source_verification"], 1)
        self.assertEqual(source_review["items"][0]["source_candidates"], [])
        self.assertIn("official_site", source_review["items"][0]["accepted_source_types"])
        self.assertTrue(all(item["status"] == "missing" for item in source_review["items"][0]["field_evidence"]))

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_official_source_review.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(source_review)), [])

    def test_build_official_source_review_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "시드후보", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            queue_path = temp_path / "work_queue.json"
            output_path = temp_path / "official_source_review.json"
            queue_path.write_text(json.dumps(work_queue, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_official_source_review.py"),
                    "--work-queue",
                    str(queue_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("pending:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total"], 1)

    def test_build_roadview_image_review_creates_visual_review_items(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))

        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))

        self.assertEqual(image_review["summary"]["total"], 1)
        self.assertEqual(image_review["summary"]["total_roadview_images"], 1)
        self.assertEqual(image_review["items"][0]["review_decision"], "pending_visual_review")
        self.assertEqual(image_review["items"][0]["review_image_samples"][0]["image_file_name"], "seed-001")
        self.assertTrue(
            all(item["status"] == "pending_visual_review" for item in image_review["items"][0]["field_evidence"])
        )

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_image_review.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(image_review)), [])

    def test_build_roadview_image_review_prefers_available_local_samples(self):
        work_queue = {
            "generated_at": "2026-07-08",
            "summary": {"total": 1, "by_task_type": {"roadview_image_review": 1}, "by_priority": {"high": 1}, "by_status": {"open": 1}},
            "items": [
                {
                    "task_id": "seed_roadview_image_review",
                    "task_type": "roadview_image_review",
                    "card": {
                        "id": "seed",
                        "name": "시드후보",
                        "region": "제주시",
                        "category": "indoor",
                        "verification_status": "partial",
                    },
                    "required_evidence": ["surface_condition"],
                }
            ],
        }
        metadata = [
            {"tourist_name": "시드후보", "image_file_name": f"sample-{index:03d}.jpg"}
            for index in range(8)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            asset_root = Path(temp_dir)
            for index in [0, 1, 3, 4, 5, 6]:
                (asset_root / f"sample-{index:03d}.jpg").write_bytes(b"placeholder")

            image_review = build_roadview_image_review(
                work_queue,
                metadata,
                asset_root=asset_root,
                generated_at=date(2026, 7, 8),
            )

        sample_names = [
            sample["image_file_name"]
            for sample in image_review["items"][0]["review_image_samples"]
        ]
        self.assertIn("sample-005.jpg", sample_names)
        self.assertNotIn("sample-007.jpg", sample_names)

    def test_build_roadview_image_review_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            queue_path = temp_path / "work_queue.json"
            metadata_path = temp_path / "image_metadata.json"
            output_path = temp_path / "roadview_image_review.json"
            queue_path.write_text(json.dumps(work_queue, ensure_ascii=False), encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_image_review.py"),
                    "--work-queue",
                    str(queue_path),
                    "--image-metadata",
                    str(metadata_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("total_roadview_images:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total"], 1)

    def test_build_roadview_image_acquisition_request_splits_priority_and_supplemental_images(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            },
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-002",
                "captured_at": "2022-07-28 09:35",
                "latitude": 33.2,
                "longitude": 126.2,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            },
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        image_review["items"][0]["review_image_samples"] = [image_review["items"][0]["review_image_samples"][0]]

        request = build_roadview_image_acquisition_request(image_review, metadata, generated_at=date(2026, 7, 8))

        self.assertEqual(request["summary"]["total_requested_images"], 2)
        self.assertEqual(request["summary"]["priority_sample_images"], 1)
        self.assertEqual(request["summary"]["supplemental_images"], 1)
        self.assertEqual(request["items"][0]["priority_images"][0]["request_tier"], "priority_visual_review_sample")
        self.assertEqual(request["items"][0]["supplemental_images"][0]["request_tier"], "supplemental_place_sequence")

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_image_acquisition_request.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(request)), [])

    def test_build_roadview_image_acquisition_request_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            review_path = temp_path / "image_review.json"
            metadata_path = temp_path / "metadata.json"
            output_path = temp_path / "acquisition_request.json"
            review_path.write_text(json.dumps(image_review, ensure_ascii=False), encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_image_acquisition_request.py"),
                    "--roadview-image-review",
                    str(review_path),
                    "--image-metadata",
                    str(metadata_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("priority:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total_places"], 1)

    def test_export_roadview_image_acquisition_csvs_writes_lists(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            },
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-002",
                "captured_at": "2022-07-28 09:35",
                "latitude": 33.2,
                "longitude": 126.2,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            },
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        image_review["items"][0]["review_image_samples"] = [image_review["items"][0]["review_image_samples"][0]]
        request = build_roadview_image_acquisition_request(image_review, metadata, generated_at=date(2026, 7, 8))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            priority_path = temp_path / "priority.csv"
            full_path = temp_path / "full.csv"
            summary_path = temp_path / "summary.csv"

            summary = export_roadview_image_acquisition_csvs(
                request,
                priority_output=priority_path,
                full_output=full_path,
                summary_output=summary_path,
            )

            self.assertEqual(summary, {"priority_rows": 1, "full_rows": 2, "summary_rows": 1})
            with priority_path.open(encoding="utf-8-sig", newline="") as file:
                priority_rows = list(csv.DictReader(file))
            with full_path.open(encoding="utf-8-sig", newline="") as file:
                full_rows = list(csv.DictReader(file))
            with summary_path.open(encoding="utf-8-sig", newline="") as file:
                summary_rows = list(csv.DictReader(file))

        self.assertEqual(priority_rows[0]["image_file_name"], "seed-001")
        self.assertEqual(len(full_rows), 2)
        self.assertEqual(summary_rows[0]["place_name"], "시드후보")

    def test_export_roadview_image_acquisition_csvs_cli_writes_lists(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        request = build_roadview_image_acquisition_request(image_review, metadata, generated_at=date(2026, 7, 8))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            request_path = temp_path / "request.json"
            priority_path = temp_path / "priority.csv"
            full_path = temp_path / "full.csv"
            summary_path = temp_path / "summary.csv"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "export_roadview_image_acquisition_csvs.py"),
                    "--acquisition-request",
                    str(request_path),
                    "--priority-output",
                    str(priority_path),
                    "--full-output",
                    str(full_path),
                    "--summary-output",
                    str(summary_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("priority:1", result.stdout)
            self.assertTrue(priority_path.exists())
            self.assertTrue(full_path.exists())
            self.assertTrue(summary_path.exists())

    def test_build_roadview_image_receipt_report_tracks_received_and_missing_files(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
            },
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-002",
                "captured_at": "2022-07-28 09:35",
                "latitude": 33.2,
                "longitude": 126.2,
                "resolution": "6720*3360",
            },
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        image_review["items"][0]["review_image_samples"] = [image_review["items"][0]["review_image_samples"][0]]
        request = build_roadview_image_acquisition_request(image_review, metadata, generated_at=date(2026, 7, 8))

        with tempfile.TemporaryDirectory() as temp_dir:
            receipt_root = Path(temp_dir)
            (receipt_root / "seed-001.jpg").write_bytes(b"received")
            (receipt_root / "outside-request.jpg").write_bytes(b"extra")

            report = build_roadview_image_receipt_report(
                request,
                receipt_root=receipt_root,
                generated_at=date(2026, 7, 8),
            )

        self.assertEqual(report["summary"]["expected_images"], 2)
        self.assertEqual(report["summary"]["received_requested_images"], 1)
        self.assertEqual(report["summary"]["missing_requested_images"], 1)
        self.assertEqual(report["summary"]["unexpected_file_count"], 1)
        self.assertEqual(report["items"][0]["status"], "partial")
        self.assertEqual(report["items"][0]["images"][0]["sha256"], hashlib.sha256(b"received").hexdigest())

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_image_receipt_report.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_build_roadview_image_receipt_report_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        request = build_roadview_image_acquisition_request(image_review, metadata, generated_at=date(2026, 7, 8))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            request_path = temp_path / "request.json"
            output_path = temp_path / "receipt_report.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_image_receipt_report.py"),
                    "--acquisition-request",
                    str(request_path),
                    "--receipt-root",
                    str(temp_path / "assets"),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                    "--skip-hash",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("missing:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total_places"], 1)

    def test_build_roadview_image_asset_manifest_tracks_local_files(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))

        with tempfile.TemporaryDirectory() as temp_dir:
            asset_root = Path(temp_dir)
            (asset_root / "seed-001.jpg").write_bytes(b"fake")

            manifest = build_roadview_image_asset_manifest(
                image_review,
                asset_root=asset_root,
                generated_at=date(2026, 7, 8),
            )

        self.assertEqual(manifest["summary"]["expected_review_sample_images"], 1)
        self.assertEqual(manifest["summary"]["available_review_sample_images"], 1)
        self.assertEqual(manifest["items"][0]["status"], "ready_for_visual_review")
        self.assertEqual(manifest["items"][0]["images"][0]["status"], "available")

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_image_asset_manifest.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(manifest)), [])

    def test_build_roadview_image_asset_manifest_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            review_path = temp_path / "roadview_image_review.json"
            output_path = temp_path / "roadview_image_asset_manifest.json"
            review_path.write_text(json.dumps(image_review, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_image_asset_manifest.py"),
                    "--roadview-image-review",
                    str(review_path),
                    "--asset-root",
                    str(temp_path / "assets"),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("missing:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total_places"], 1)

    def test_build_roadview_visual_review_sheet_creates_manual_input_rows(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_root = Path(temp_dir)
            (asset_root / "seed-001.jpg").write_bytes(b"fake")
            manifest = build_roadview_image_asset_manifest(
                image_review,
                asset_root=asset_root,
                generated_at=date(2026, 7, 8),
            )

        sheet = build_roadview_visual_review_sheet(image_review, manifest, generated_at=date(2026, 7, 8))

        self.assertEqual(sheet["summary"]["total_places"], 1)
        self.assertEqual(sheet["summary"]["by_status"]["open"], 1)
        self.assertEqual(sheet["summary"]["total_field_results"], 4)
        self.assertEqual(sheet["items"][0]["field_results"][0]["status"], "pending_visual_review")

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_visual_review_sheet.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(sheet)), [])

    def test_apply_roadview_visual_review_sheet_updates_image_review(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        manifest = build_roadview_image_asset_manifest(
            image_review,
            asset_root=Path("missing"),
            generated_at=date(2026, 7, 8),
        )
        sheet = build_roadview_visual_review_sheet(image_review, manifest, generated_at=date(2026, 7, 8))
        for result in sheet["items"][0]["field_results"]:
            result["status"] = "verified"
            result["evidence_image_file_names"] = ["seed-001"]
            result["reviewer_note"] = f"{result['field']} 확인"
            result["reviewer"] = "tester"
            result["reviewed_at"] = "2026-07-08"

        applied = apply_roadview_visual_review_sheet(image_review, sheet, generated_at=date(2026, 7, 8))
        updated_review = applied["updated_roadview_image_review"]
        apply_report = applied["apply_report"]

        self.assertEqual(updated_review["items"][0]["status"], "resolved")
        self.assertEqual(updated_review["items"][0]["review_decision"], "verified_accessible_route")
        self.assertEqual(apply_report["summary"]["by_action"]["applied"], 1)
        self.assertEqual(apply_report["summary"]["by_new_status"]["resolved"], 1)

        review_schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_image_review.schema.json").read_text(encoding="utf-8")
        )
        report_schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_visual_review_apply_report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(Draft202012Validator(review_schema).iter_errors(updated_review)), [])
        self.assertEqual(list(Draft202012Validator(report_schema).iter_errors(apply_report)), [])

    def test_roadview_visual_review_sheet_clis_write_reports(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        manifest = build_roadview_image_asset_manifest(
            image_review,
            asset_root=Path("missing"),
            generated_at=date(2026, 7, 8),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            review_path = temp_path / "image_review.json"
            manifest_path = temp_path / "asset_manifest.json"
            sheet_path = temp_path / "visual_review_sheet.json"
            updated_path = temp_path / "updated_image_review.json"
            report_path = temp_path / "apply_report.json"
            review_path.write_text(json.dumps(image_review, ensure_ascii=False), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            build_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_visual_review_sheet.py"),
                    "--roadview-image-review",
                    str(review_path),
                    "--image-asset-manifest",
                    str(manifest_path),
                    "--output",
                    str(sheet_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(build_result.returncode, 0, build_result.stderr)
            self.assertIn("fields:4", build_result.stdout)

            apply_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "apply_roadview_visual_review_sheet.py"),
                    "--roadview-image-review",
                    str(review_path),
                    "--visual-review-sheet",
                    str(sheet_path),
                    "--output",
                    str(updated_path),
                    "--report-output",
                    str(report_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            self.assertIn("pending:1", apply_result.stdout)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["summary"]["total"], 1)

    def test_build_crowd_policy_review_resolves_policy_tasks(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "시드후보", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))

        review = build_crowd_policy_review(work_queue, generated_at=date(2026, 7, 8))

        self.assertEqual(review["summary"]["total"], 1)
        self.assertEqual(review["summary"]["by_status"]["resolved"], 1)
        self.assertTrue(review["items"][0]["policy"]["operating_calendar_check_required"])

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_crowd_policy_review.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(review)), [])

    def test_build_category_refinement_review_resolves_other_categories(self):
        seed_cards = [draft_card("jeju_roadview_place_104", "스누피가든", category="other")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "스누피가든", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))

        review = build_category_refinement_review(work_queue, generated_at=date(2026, 7, 8))

        self.assertEqual(review["summary"]["total"], 1)
        self.assertEqual(review["items"][0]["recommended_category"], "rest_area")
        self.assertIn("weather_sensitive", review["items"][0]["recommended_situation_tags"])

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_category_refinement_review.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(review)), [])

    def test_build_service_seed_promotion_readiness_blocks_unfinished_gates(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))

        readiness = build_service_seed_promotion_readiness(
            seed_cards,
            work_queue,
            official_review,
            image_review,
            generated_at=date(2026, 7, 8),
        )

        self.assertEqual(readiness["summary"]["ready_count"], 0)
        self.assertEqual(readiness["summary"]["blocked_count"], 1)
        item = readiness["items"][0]
        self.assertEqual(item["promotion_decision"], "blocked_pending_hardening")
        self.assertEqual(item["gate_statuses"]["seed_card_hidden"], "pass")
        self.assertIn("official_source_verified", item["blocking_gates"])
        self.assertIn("roadview_image_verified", item["blocking_gates"])
        self.assertIn("crowd_policy_resolved", item["blocking_gates"])

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_service_seed_promotion_readiness.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(readiness)), [])

    def test_build_service_seed_promotion_readiness_accepts_policy_reviews(self):
        seed_cards = [draft_card("jeju_roadview_place_104", "스누피가든", category="other")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "스누피가든",
                "tourist_name_en": "SNOOPY",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        crowd_review = build_crowd_policy_review(work_queue, generated_at=date(2026, 7, 8))
        category_review = build_category_refinement_review(work_queue, generated_at=date(2026, 7, 8))

        readiness = build_service_seed_promotion_readiness(
            seed_cards,
            work_queue,
            official_review,
            image_review,
            crowd_review,
            category_review,
            generated_at=date(2026, 7, 8),
        )

        blockers = readiness["items"][0]["blocking_gates"]
        self.assertNotIn("crowd_policy_resolved", blockers)
        self.assertNotIn("category_refinement_resolved", blockers)
        self.assertIn("roadview_image_verified", blockers)

    def test_promotion_readiness_allows_official_visual_fallback_fields(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        official_item = official_review["items"][0]
        official_item["status"] = "in_progress"
        official_item["review_decision"] = "source_found_but_incomplete"
        official_item["source_candidates"] = [
            {
                "url": "https://www.data.go.kr/data/15109153/fileData.do",
                "title": "공공데이터",
                "source_type": "public_agency",
                "evidence_status": "usable_accessibility_detail",
                "matched_place_name": "시드후보",
                "notes": "공식 출처 후보",
            }
        ]
        for evidence in official_item["field_evidence"]:
            if evidence["field"] in {"slope_or_stairs", "surface_condition"}:
                evidence["status"] = "missing"
            else:
                evidence["status"] = "candidate_found"
                evidence["source_url"] = "https://www.data.go.kr/data/15109153/fileData.do"
                evidence["note"] = "공식 출처 후보 확인"
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        crowd_review = build_crowd_policy_review(work_queue, generated_at=date(2026, 7, 8))

        readiness = build_service_seed_promotion_readiness(
            seed_cards,
            work_queue,
            official_review,
            image_review,
            crowd_review,
            generated_at=date(2026, 7, 8),
        )

        item = readiness["items"][0]
        self.assertNotIn("official_source_verified", item["blocking_gates"])
        self.assertIn("roadview_image_verified", item["blocking_gates"])
        self.assertEqual(
            item["official_source_review_status"]["visual_fallback_fields"],
            ["slope_or_stairs", "surface_condition"],
        )
        self.assertEqual(item["official_source_review_status"]["blocking_missing_fields"], [])

    def test_build_service_seed_promotion_readiness_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            seed_path = temp_path / "seed_cards.json"
            queue_path = temp_path / "work_queue.json"
            official_path = temp_path / "official_review.json"
            image_path = temp_path / "image_review.json"
            output_path = temp_path / "promotion_readiness.json"
            seed_path.write_text(json.dumps(seed_cards, ensure_ascii=False), encoding="utf-8")
            queue_path.write_text(json.dumps(work_queue, ensure_ascii=False), encoding="utf-8")
            official_path.write_text(json.dumps(official_review, ensure_ascii=False), encoding="utf-8")
            image_path.write_text(json.dumps(image_review, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_service_seed_promotion_readiness.py"),
                    "--seed-cards",
                    str(seed_path),
                    "--work-queue",
                    str(queue_path),
                    "--official-source-review",
                    str(official_path),
                    "--roadview-image-review",
                    str(image_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("blocked:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["total"], 1)

    def test_build_service_seed_active_candidates_promotes_ready_cards(self):
        seed_cards = [draft_card("jeju_roadview_place_104", "스누피가든", category="other")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "스누피가든",
                "tourist_name_en": "SNOOPY",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
                "source": {
                    "name": "제주특별자치도",
                    "url": "https://www.data.go.kr/data/15109158/fileData.do",
                    "dataset_name": "사회적약자 시설 데이터(로드뷰) 구축 이미지 메타데이터",
                    "license": "이용허락범위 제한 없음",
                },
            }
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        official_item = official_review["items"][0]
        official_item["status"] = "resolved"
        official_item["review_decision"] = "verified_usable_source"
        official_item["source_candidates"] = [
            {
                "url": "https://access.visitkorea.or.kr/ms/detail.do?cotId=test",
                "title": "스누피가든 - 열린관광 모두의 여행",
                "source_type": "open_tourism_accessibility_detail",
                "evidence_status": "usable_accessibility_detail",
                "matched_place_name": "스누피가든",
                "notes": "접근성 상세 출처",
            }
        ]
        for evidence in official_item["field_evidence"]:
            evidence["status"] = "candidate_found"
            evidence["source_url"] = "https://access.visitkorea.or.kr/ms/detail.do?cotId=test"
            evidence["note"] = "공식 출처 후보 확인"
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        image_review["items"][0]["status"] = "resolved"
        image_review["items"][0]["review_decision"] = "verified_accessible_route"
        for evidence in image_review["items"][0]["field_evidence"]:
            evidence["status"] = "verified"
            evidence["note"] = "수동 이미지 검수 완료"
        crowd_review = build_crowd_policy_review(work_queue, generated_at=date(2026, 7, 8))
        category_review = build_category_refinement_review(work_queue, generated_at=date(2026, 7, 8))
        readiness = build_service_seed_promotion_readiness(
            seed_cards,
            work_queue,
            official_review,
            image_review,
            crowd_review,
            category_review,
            generated_at=date(2026, 7, 8),
        )

        result = build_service_seed_active_candidates(
            seed_cards,
            readiness,
            official_review,
            category_review,
            generated_at=date(2026, 7, 8),
        )

        self.assertEqual(result["promotion_report"]["summary"]["promoted_count"], 1)
        active_card = result["active_candidates"][0]
        self.assertEqual(active_card["status"], "active")
        self.assertEqual(active_card["category"], "rest_area")
        self.assertEqual(active_card["verification"]["status"], "verified")
        self.assertEqual(active_card["verification"]["missing_fields"], [])
        self.assertIn("weather_sensitive", active_card["situation_tags"])
        self.assertEqual(active_card["accessibility"]["slope_or_stairs"]["source_ref"], "roadview_visual_review")

        card_schema = json.loads(
            (ROOT / "data" / "schemas" / "accessibility_place_card.schema.json").read_text(encoding="utf-8")
        )
        report_schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_service_seed_active_candidate_report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(Draft202012Validator(card_schema).iter_errors(active_card)), [])
        self.assertEqual(list(Draft202012Validator(report_schema).iter_errors(result["promotion_report"])), [])

    def test_build_service_seed_active_candidates_cli_writes_empty_when_blocked(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "시드후보", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        readiness = build_service_seed_promotion_readiness(
            seed_cards,
            work_queue,
            official_review,
            image_review,
            generated_at=date(2026, 7, 8),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            seed_path = temp_path / "seed_cards.json"
            readiness_path = temp_path / "readiness.json"
            official_path = temp_path / "official.json"
            output_path = temp_path / "active_candidates.json"
            report_path = temp_path / "active_report.json"
            seed_path.write_text(json.dumps(seed_cards, ensure_ascii=False), encoding="utf-8")
            readiness_path.write_text(json.dumps(readiness, ensure_ascii=False), encoding="utf-8")
            official_path.write_text(json.dumps(official_review, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_service_seed_active_candidates.py"),
                    "--seed-cards",
                    str(seed_path),
                    "--promotion-readiness",
                    str(readiness_path),
                    "--official-source-review",
                    str(official_path),
                    "--output",
                    str(output_path),
                    "--report-output",
                    str(report_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("promoted:0", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), [])
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["summary"]["blocked_count"], 1)

    def test_build_service_seed_gate_status_splits_receipt_and_visual_gates(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-001",
                "captured_at": "2022-07-28 09:34",
                "latitude": 33.1,
                "longitude": 126.1,
                "resolution": "6720*3360",
            },
            {
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "image_file_name": "seed-002",
                "captured_at": "2022-07-28 09:35",
                "latitude": 33.2,
                "longitude": 126.2,
                "resolution": "6720*3360",
            },
        ]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        image_review["items"][0]["review_image_samples"] = [image_review["items"][0]["review_image_samples"][0]]
        acquisition_request = build_roadview_image_acquisition_request(
            image_review,
            metadata,
            generated_at=date(2026, 7, 8),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            asset_root = Path(temp_dir)
            (asset_root / "seed-001.jpg").write_bytes(b"received-sample")
            receipt_report = build_roadview_image_receipt_report(
                acquisition_request,
                receipt_root=asset_root,
                generated_at=date(2026, 7, 8),
            )
            asset_manifest = build_roadview_image_asset_manifest(
                image_review,
                asset_root=asset_root,
                generated_at=date(2026, 7, 8),
            )

        visual_sheet = build_roadview_visual_review_sheet(
            image_review,
            asset_manifest,
            generated_at=date(2026, 7, 8),
        )
        crowd_review = build_crowd_policy_review(work_queue, generated_at=date(2026, 7, 8))
        category_review = build_category_refinement_review(work_queue, generated_at=date(2026, 7, 8))
        readiness = build_service_seed_promotion_readiness(
            seed_cards,
            work_queue,
            official_review,
            image_review,
            crowd_review,
            category_review,
            generated_at=date(2026, 7, 8),
        )
        active_report = build_service_seed_active_candidates(
            seed_cards,
            readiness,
            official_review,
            category_review,
            generated_at=date(2026, 7, 8),
        )["promotion_report"]

        gate_status = build_service_seed_gate_status(
            acquisition_request,
            receipt_report,
            asset_manifest,
            visual_sheet,
            readiness,
            active_report,
            generated_at=date(2026, 7, 8),
        )

        self.assertEqual(gate_status["overall_status"], "blocked")
        self.assertEqual(gate_status["current_primary_stage"], "awaiting_image_receipt")
        self.assertEqual(gate_status["summary"]["missing_requested_images"], 1)
        self.assertEqual(gate_status["items"][0]["gate_statuses"]["image_receipt_complete"], "fail")
        self.assertEqual(gate_status["items"][0]["gate_statuses"]["review_samples_available"], "pass")
        self.assertEqual(gate_status["items"][0]["gate_statuses"]["visual_review_sheet_open"], "pass")

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_service_seed_gate_status.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(gate_status)), [])

    def test_build_service_seed_gate_status_cli_writes_report(self):
        seed_cards = [draft_card("jeju_roadview_seed_001", "시드후보")]
        seed_cards[0]["status"] = "hidden"
        metadata = [{"tourist_name": "시드후보", "image_file_name": "seed-001", "captured_at": "2022-07-28 09:34"}]
        seed_review = build_service_seed_review(seed_cards, metadata, generated_at=date(2026, 7, 8))
        work_queue = build_service_seed_work_queue(seed_review, generated_at=date(2026, 7, 8))
        official_review = build_official_source_review(work_queue, generated_at=date(2026, 7, 8))
        image_review = build_roadview_image_review(work_queue, metadata, generated_at=date(2026, 7, 8))
        acquisition_request = build_roadview_image_acquisition_request(image_review, metadata, generated_at=date(2026, 7, 8))
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            receipt_report = build_roadview_image_receipt_report(
                acquisition_request,
                receipt_root=temp_path / "assets",
                generated_at=date(2026, 7, 8),
                hash_files=False,
            )
            asset_manifest = build_roadview_image_asset_manifest(
                image_review,
                asset_root=temp_path / "assets",
                generated_at=date(2026, 7, 8),
            )
            visual_sheet = build_roadview_visual_review_sheet(
                image_review,
                asset_manifest,
                generated_at=date(2026, 7, 8),
            )
            readiness = build_service_seed_promotion_readiness(
                seed_cards,
                work_queue,
                official_review,
                image_review,
                generated_at=date(2026, 7, 8),
            )
            active_report = build_service_seed_active_candidates(
                seed_cards,
                readiness,
                official_review,
                generated_at=date(2026, 7, 8),
            )["promotion_report"]
            acquisition_path = temp_path / "acquisition.json"
            receipt_path = temp_path / "receipt.json"
            asset_path = temp_path / "asset.json"
            visual_path = temp_path / "visual.json"
            readiness_path = temp_path / "readiness.json"
            active_path = temp_path / "active_report.json"
            output_path = temp_path / "gate_status.json"
            acquisition_path.write_text(json.dumps(acquisition_request, ensure_ascii=False), encoding="utf-8")
            receipt_path.write_text(json.dumps(receipt_report, ensure_ascii=False), encoding="utf-8")
            asset_path.write_text(json.dumps(asset_manifest, ensure_ascii=False), encoding="utf-8")
            visual_path.write_text(json.dumps(visual_sheet, ensure_ascii=False), encoding="utf-8")
            readiness_path.write_text(json.dumps(readiness, ensure_ascii=False), encoding="utf-8")
            active_path.write_text(json.dumps(active_report, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_service_seed_gate_status.py"),
                    "--acquisition-request",
                    str(acquisition_path),
                    "--receipt-report",
                    str(receipt_path),
                    "--image-asset-manifest",
                    str(asset_path),
                    "--visual-review-sheet",
                    str(visual_path),
                    "--promotion-readiness",
                    str(readiness_path),
                    "--active-candidate-report",
                    str(active_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("stage:awaiting_image_receipt", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["blocked_count"], 1)


if __name__ == "__main__":
    unittest.main()
