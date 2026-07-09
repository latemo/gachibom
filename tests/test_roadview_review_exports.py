import csv
import json
import subprocess
import sys
import tempfile
import unittest
import shutil
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.roadview_review_exports import (
    apply_visual_review_decision_csv,
    build_provider_404_recovery_request_markdown,
    build_roadview_visual_review_board_html,
    build_shareable_visual_review_package,
    build_visual_review_packets,
    export_provider_404_image_request_csv,
    export_visual_review_decision_csv,
    merge_visual_review_decision_csvs,
    validate_visual_review_share_package,
)


ROOT = Path(__file__).resolve().parents[1]


def sample_provider_404_report():
    return {
        "generated_at": "2026-07-08",
        "source_endpoint": "https://gis.jeju.go.kr/images/roadview",
        "summary": {
            "provider_404_images": 1,
            "affected_places": 1,
            "by_place": {"시드후보": 1},
            "by_request_tier": {"supplemental_place_sequence": 1},
        },
        "items": [
            {
                "card_id": "jeju_roadview_seed_001",
                "place_name": "시드후보",
                "image_file_name": "SEED-1-001",
                "request_tier": "supplemental_place_sequence",
                "tourist_name": "시드후보",
                "tourist_name_en": "SEED",
                "captured_at": "2022-07-28 09:34",
                "source_url": "https://gis.jeju.go.kr/images/roadview/SEED/SEED-1-001.jpg",
                "error": "HTTP Error 404: Not Found",
            }
        ],
    }


def sample_visual_review_sheet():
    return {
        "generated_at": "2026-07-08",
        "summary": {
            "total_places": 1,
            "total_field_results": 1,
            "by_field_status": {"pending_visual_review": 1},
        },
        "items": [
            {
                "task_id": "jeju_roadview_seed_001_roadview_image_review",
                "card": {
                    "id": "jeju_roadview_seed_001",
                    "name": "시드후보",
                    "region": "제주시",
                    "category": "indoor",
                    "verification_status": "partial",
                },
                "status": "open",
                "review_decision": "pending_reviewer_input",
                "review_image_samples": [
                    {
                        "image_file_name": "SEED-1-002",
                        "captured_at": "2022-07-28 09:35",
                        "latitude": 33.4,
                        "longitude": 126.5,
                        "resolution": "6720*3360",
                        "present_path": "data/raw/roadview_images/SEED-1-002.jpg",
                        "status": "available",
                    }
                ],
                "field_results": [
                    {
                        "field": "entrance_step_or_ramp",
                        "status": "pending_visual_review",
                        "image_file_names": ["SEED-1-002"],
                        "evidence_image_file_names": [],
                        "reviewer_note": "",
                        "reviewer": None,
                        "reviewed_at": None,
                    }
                ],
            }
        ],
    }


def sample_visual_review_sheet_with_image(image_path: Path):
    sheet = sample_visual_review_sheet()
    sheet["items"][0]["review_image_samples"][0]["present_path"] = str(image_path)
    return sheet


class RoadviewReviewExportsTests(unittest.TestCase):
    def test_export_provider_404_image_request_csv_writes_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "provider_404.csv"
            summary = export_provider_404_image_request_csv(sample_provider_404_report(), output_path)
            with output_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(summary, {"rows": 1})
        self.assertEqual(rows[0]["place_name"], "시드후보")
        self.assertEqual(rows[0]["image_file_name"], "SEED-1-001")

    def test_build_provider_404_recovery_request_markdown_mentions_counts(self):
        markdown = build_provider_404_recovery_request_markdown(
            sample_provider_404_report(),
            generated_at=date(2026, 7, 8),
        )

        self.assertIn("누락 원본: 1장", markdown)
        self.assertIn("| 시드후보 | 1 |", markdown)
        self.assertIn("data/roadview_provider_404_image_request.csv", markdown)

    def test_build_roadview_visual_review_board_html_links_local_images(self):
        sheet = sample_visual_review_sheet()
        sheet["items"][0]["field_results"][0]["ai_suggestion"] = {
            "status": "verified",
            "evidence_image_file_names": ["SEED-1-002"],
            "note": "자동 판정 초안: 평탄 진입으로 보임",
            "confidence": "medium",
        }
        html = build_roadview_visual_review_board_html(
            sheet,
            provider_404_report=sample_provider_404_report(),
            output_path=Path("docs/roadview_visual_review_board.html"),
            generated_at=date(2026, 7, 8),
        )

        self.assertIn("로드뷰 시각 검수 보드", html)
        self.assertIn("../data/raw/roadview_images/SEED-1-002.jpg", html)
        self.assertIn("출입구 단차/경사로", html)
        self.assertIn("자동 판정 초안: 평탄 진입으로 보임", html)
        self.assertIn("자동 판정 승인", html)
        self.assertIn("판정 파일 내려받기", html)
        self.assertIn("난해 항목 확인 가이드", html)
        self.assertIn("왜 사람이 다시 봐야 하나", html)
        self.assertIn("data-filter=\"attention\"", html)
        self.assertIn("data-lightbox-image", html)
        self.assertIn("이미지 확대 보기", html)
        self.assertIn("닫기", html)
        self.assertIn("showOpenFilePicker", html)
        self.assertIn("서버 404", html)

    def test_export_visual_review_decision_csv_writes_field_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "decisions.csv"
            summary = export_visual_review_decision_csv(sample_visual_review_sheet(), output_path)
            with output_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(summary, {"rows": 1})
        self.assertEqual(rows[0]["field"], "entrance_step_or_ramp")
        self.assertIn("ai_suggested_status", rows[0])
        self.assertIn("human_final_status", rows[0])
        self.assertEqual(rows[0]["available_image_file_names"], "SEED-1-002")

    def test_export_visual_review_decision_csv_writes_ai_suggestion(self):
        sheet = sample_visual_review_sheet()
        sheet["items"][0]["field_results"][0]["ai_suggestion"] = {
            "status": "needs_follow_up",
            "evidence_image_file_names": ["SEED-1-002"],
            "note": "자동 판정 초안: 출입구 단차 확인 필요",
            "confidence": "medium",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "decisions.csv"
            export_visual_review_decision_csv(sheet, output_path)
            with output_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(rows[0]["ai_suggested_status"], "needs_follow_up")
        self.assertEqual(rows[0]["ai_suggested_evidence_image_file_names"], "SEED-1-002")
        self.assertEqual(rows[0]["ai_suggested_note"], "자동 판정 초안: 출입구 단차 확인 필요")
        self.assertEqual(rows[0]["ai_confidence"], "medium")

    def test_apply_visual_review_decision_csv_updates_sheet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "decisions.csv"
            csv_path.write_text(
                (
                    "card_id,place_name,field,field_label,ai_suggested_status,ai_suggested_evidence_image_file_names,"
                    "ai_suggested_note,ai_confidence,human_final_status,human_evidence_image_file_names,"
                    "human_reviewer_note,human_reviewer,human_reviewed_at,available_image_file_names\n"
                    "jeju_roadview_seed_001,시드후보,entrance_step_or_ramp,출입구 단차/경사로,"
                    ",,,,verified,SEED-1-002,단차 없는 출입 동선 확인,,,"
                    "SEED-1-002\n"
                ),
                encoding="utf-8-sig",
            )

            result = apply_visual_review_decision_csv(
                sample_visual_review_sheet(),
                csv_path,
                reviewer="operator",
                reviewed_at=date(2026, 7, 8),
                generated_at=date(2026, 7, 8),
            )

        field_result = result["updated_visual_review_sheet"]["items"][0]["field_results"][0]
        self.assertEqual(field_result["status"], "verified")
        self.assertEqual(field_result["evidence_image_file_names"], ["SEED-1-002"])
        self.assertEqual(field_result["reviewer"], "operator")
        self.assertEqual(result["import_report"]["summary"]["applied"], 1)

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_visual_review_decision_import_report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(result["import_report"])), [])

    def test_apply_visual_review_decision_csv_ignores_ai_suggestion_without_human_final(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "decisions.csv"
            csv_path.write_text(
                (
                    "card_id,place_name,field,field_label,ai_suggested_status,ai_suggested_evidence_image_file_names,"
                    "ai_suggested_note,ai_confidence,human_final_status,human_evidence_image_file_names,"
                    "human_reviewer_note,human_reviewer,human_reviewed_at,available_image_file_names\n"
                    "jeju_roadview_seed_001,시드후보,entrance_step_or_ramp,출입구 단차/경사로,"
                    "verified,SEED-1-002,자동 판정 초안,medium,,,,,,SEED-1-002\n"
                ),
                encoding="utf-8-sig",
            )

            result = apply_visual_review_decision_csv(
                sample_visual_review_sheet(),
                csv_path,
                reviewer="operator",
                reviewed_at=date(2026, 7, 8),
                generated_at=date(2026, 7, 8),
            )

        self.assertEqual(result["import_report"]["summary"]["applied"], 0)
        self.assertEqual(result["import_report"]["summary"]["skipped"], 1)
        self.assertEqual(
            result["updated_visual_review_sheet"]["items"][0]["field_results"][0]["status"],
            "pending_visual_review",
        )

    def test_apply_visual_review_decision_csv_rejects_unknown_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "decisions.csv"
            csv_path.write_text(
                (
                    "card_id,place_name,field,field_label,ai_suggested_status,ai_suggested_evidence_image_file_names,"
                    "ai_suggested_note,ai_confidence,human_final_status,human_evidence_image_file_names,"
                    "human_reviewer_note,human_reviewer,human_reviewed_at,available_image_file_names\n"
                    "jeju_roadview_seed_001,시드후보,entrance_step_or_ramp,출입구 단차/경사로,"
                    ",,,,verified,UNKNOWN-1-001,근거 이미지 오류,,,"
                    "SEED-1-002\n"
                ),
                encoding="utf-8-sig",
            )

            result = apply_visual_review_decision_csv(
                sample_visual_review_sheet(),
                csv_path,
                reviewer="operator",
                reviewed_at=date(2026, 7, 8),
                generated_at=date(2026, 7, 8),
            )

        self.assertEqual(result["import_report"]["summary"]["invalid"], 1)
        self.assertEqual(
            result["updated_visual_review_sheet"]["items"][0]["field_results"][0]["status"],
            "pending_visual_review",
        )

    def test_provider_404_package_cli_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_path = temp_path / "provider_404.json"
            csv_path = temp_path / "provider_404.csv"
            message_path = temp_path / "message.md"
            report_path.write_text(json.dumps(sample_provider_404_report(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "export_roadview_provider_404_request_package.py"),
                    "--provider-404-report",
                    str(report_path),
                    "--csv-output",
                    str(csv_path),
                    "--message-output",
                    str(message_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("rows:1", result.stdout)
            self.assertTrue(csv_path.exists())
            self.assertTrue(message_path.exists())

    def test_visual_review_board_cli_writes_html(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sheet_path = temp_path / "sheet.json"
            report_path = temp_path / "provider_404.json"
            output_path = temp_path / "board.html"
            sheet_path.write_text(json.dumps(sample_visual_review_sheet(), ensure_ascii=False), encoding="utf-8")
            report_path.write_text(json.dumps(sample_provider_404_report(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_visual_review_board.py"),
                    "--visual-review-sheet",
                    str(sheet_path),
                    "--provider-404-report",
                    str(report_path),
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
            self.assertIn("places:1", result.stdout)
            self.assertIn("로드뷰 시각 검수 보드", output_path.read_text(encoding="utf-8"))

    def test_visual_review_decision_csv_clis_write_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sheet_path = temp_path / "sheet.json"
            csv_path = temp_path / "decisions.csv"
            output_path = temp_path / "updated_sheet.json"
            report_path = temp_path / "import_report.json"
            sheet_path.write_text(json.dumps(sample_visual_review_sheet(), ensure_ascii=False), encoding="utf-8")

            export_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "export_roadview_visual_review_decisions_csv.py"),
                    "--visual-review-sheet",
                    str(sheet_path),
                    "--output",
                    str(csv_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(export_result.returncode, 0, export_result.stderr)
            self.assertIn("rows:1", export_result.stdout)

            with csv_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
                fieldnames = rows[0].keys()
            rows[0]["human_final_status"] = "missing"
            rows[0]["human_reviewer_note"] = "이미지만으로 확인 불가"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            apply_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "apply_roadview_visual_review_decisions_csv.py"),
                    "--visual-review-sheet",
                    str(sheet_path),
                    "--decisions-csv",
                    str(csv_path),
                    "--output",
                    str(output_path),
                    "--report-output",
                    str(report_path),
                    "--reviewer",
                    "operator",
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            self.assertIn("applied:1", apply_result.stdout)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8"))["items"][0]["field_results"][0]["status"],
                "missing",
            )

    def test_build_visual_review_packets_writes_contact_sheet_and_place_csv(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "SEED-1-002.jpg"
            Image.new("RGB", (120, 60), (40, 90, 120)).save(image_path)
            report = build_visual_review_packets(
                sample_visual_review_sheet_with_image(image_path),
                contact_sheet_dir=temp_path / "contact_sheets",
                csv_dir=temp_path / "csv",
                index_output=temp_path / "index.html",
                generated_at=date(2026, 7, 8),
            )

            self.assertEqual(report["total_places"], 1)
            self.assertEqual(report["contact_sheet_count"], 1)
            self.assertEqual(report["decision_csv_count"], 1)
            index_html = (temp_path / "index.html").read_text(encoding="utf-8")
            self.assertIn("data-lightbox-image", index_html)
            self.assertIn("이미지 확대 보기", index_html)
            self.assertIn("닫기", index_html)
            schema = json.loads(
                (ROOT / "data" / "schemas" / "roadview_visual_review_packet_report.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_visual_review_packets_cli_writes_outputs(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "SEED-1-002.jpg"
            sheet_path = temp_path / "sheet.json"
            index_path = temp_path / "index.html"
            report_path = temp_path / "packet_report.json"
            Image.new("RGB", (120, 60), (40, 90, 120)).save(image_path)
            sheet_path.write_text(
                json.dumps(sample_visual_review_sheet_with_image(image_path), ensure_ascii=False),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_visual_review_packets.py"),
                    "--visual-review-sheet",
                    str(sheet_path),
                    "--contact-sheet-dir",
                    str(temp_path / "contact_sheets"),
                    "--csv-dir",
                    str(temp_path / "csv"),
                    "--index-output",
                    str(index_path),
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
            self.assertIn("places:1", result.stdout)
            self.assertTrue(index_path.exists())
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["total_places"], 1)

    def test_build_shareable_visual_review_package_copies_assets(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "SEED-1-002.jpg"
            package_dir = temp_path / "share"
            Image.new("RGB", (1200, 600), (40, 90, 120)).save(image_path)

            report = build_shareable_visual_review_package(
                sample_visual_review_sheet_with_image(image_path),
                package_dir=package_dir,
                provider_404_report=sample_provider_404_report(),
                generated_at=date(2026, 7, 8),
                max_image_width=400,
            )

            index_html = (package_dir / "index.html").read_text(encoding="utf-8")
            self.assertEqual(report["copied_image_count"], 1)
            self.assertIn("assets/SEED-1-002.jpg", index_html)
            self.assertIn("서버 404", index_html)
            self.assertIn("<span>1</span>", index_html)
            self.assertNotIn("data/raw/roadview_images", index_html)
            self.assertTrue((package_dir / "assets" / "SEED-1-002.jpg").exists())

    def test_share_package_cli_writes_zip(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "SEED-1-002.jpg"
            sheet_path = temp_path / "sheet.json"
            provider_404_path = temp_path / "provider_404.json"
            package_dir = temp_path / "share"
            zip_path = temp_path / "share.zip"
            report_path = temp_path / "share_report.json"
            Image.new("RGB", (1200, 600), (40, 90, 120)).save(image_path)
            sheet_path.write_text(
                json.dumps(sample_visual_review_sheet_with_image(image_path), ensure_ascii=False),
                encoding="utf-8",
            )
            provider_404_path.write_text(json.dumps(sample_provider_404_report(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_visual_review_share_package.py"),
                    "--visual-review-sheet",
                    str(sheet_path),
                    "--provider-404-report",
                    str(provider_404_path),
                    "--package-dir",
                    str(package_dir),
                    "--zip-output",
                    str(zip_path),
                    "--report-output",
                    str(report_path),
                    "--max-image-width",
                    "400",
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("images:1", result.stdout)
            self.assertTrue(zip_path.exists())
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["copied_image_count"], 1)

    def test_validate_visual_review_share_package_reports_checksum(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "SEED-1-002.jpg"
            package_dir = temp_path / "share"
            zip_path = temp_path / "share.zip"
            Image.new("RGB", (1200, 600), (40, 90, 120)).save(image_path)
            build_shareable_visual_review_package(
                sample_visual_review_sheet_with_image(image_path),
                package_dir=package_dir,
                generated_at=date(2026, 7, 8),
                max_image_width=400,
            )
            shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=package_dir)

            report = validate_visual_review_share_package(
                package_dir=package_dir,
                zip_path=zip_path,
                expected_assets=1,
                expected_contact_sheets=1,
                expected_place_csvs=1,
                generated_at=date(2026, 7, 8),
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["asset_count"], 1)
        self.assertEqual(len(report["summary"]["zip_sha256"]), 64)

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_visual_review_share_validation_report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_validate_share_package_cli_writes_report(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "SEED-1-002.jpg"
            package_dir = temp_path / "share"
            zip_path = temp_path / "share.zip"
            report_path = temp_path / "validation.json"
            Image.new("RGB", (1200, 600), (40, 90, 120)).save(image_path)
            build_shareable_visual_review_package(
                sample_visual_review_sheet_with_image(image_path),
                package_dir=package_dir,
                generated_at=date(2026, 7, 8),
                max_image_width=400,
            )
            shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=package_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate_roadview_visual_review_share_package.py"),
                    "--package-dir",
                    str(package_dir),
                    "--zip-path",
                    str(zip_path),
                    "--output",
                    str(report_path),
                    "--expected-assets",
                    "1",
                    "--expected-contact-sheets",
                    "1",
                    "--expected-place-csvs",
                    "1",
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("status:pass", result.stdout)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["status"], "pass")

    def test_merge_visual_review_decision_csvs_combines_place_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_dir = temp_path / "csv"
            csv_dir.mkdir()
            sheet = sample_visual_review_sheet()
            export_visual_review_decision_csv(sheet, csv_dir / "one.csv")
            export_visual_review_decision_csv(sheet, csv_dir / "two.csv")
            output_path = temp_path / "merged.csv"

            summary = merge_visual_review_decision_csvs(csv_dir, output_path)
            with output_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(summary, {"files": 2, "rows": 2})
        self.assertEqual(len(rows), 2)

    def test_merge_visual_review_decision_csvs_cli_writes_master_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_dir = temp_path / "csv"
            csv_dir.mkdir()
            export_visual_review_decision_csv(sample_visual_review_sheet(), csv_dir / "one.csv")
            output_path = temp_path / "merged.csv"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "merge_roadview_visual_review_decision_csvs.py"),
                    "--csv-dir",
                    str(csv_dir),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("rows:1", result.stdout)
            self.assertTrue(output_path.exists())

    def test_visual_review_pipeline_cli_blocks_invalid_decisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sheet_path = temp_path / "sheet.json"
            decisions_path = temp_path / "decisions.csv"
            import_report_path = temp_path / "import_report.json"
            pipeline_report_path = temp_path / "pipeline_report.json"
            recovery_report_path = temp_path / "recovery_report.json"
            recovery_markdown_path = temp_path / "recovery_report.md"
            sheet_path.write_text(json.dumps(sample_visual_review_sheet(), ensure_ascii=False), encoding="utf-8")
            decisions_path.write_text(
                (
                    "card_id,place_name,field,field_label,ai_suggested_status,ai_suggested_evidence_image_file_names,"
                    "ai_suggested_note,ai_confidence,human_final_status,human_evidence_image_file_names,"
                    "human_reviewer_note,human_reviewer,human_reviewed_at,available_image_file_names\n"
                    "jeju_roadview_seed_001,시드후보,entrance_step_or_ramp,출입구 단차/경사로,"
                    ",,,,verified,UNKNOWN-1-001,근거 이미지 오류,,,"
                    "SEED-1-002\n"
                ),
                encoding="utf-8-sig",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_roadview_visual_review_pipeline.py"),
                    "--visual-review-sheet",
                    str(sheet_path),
                    "--decisions-csv",
                    str(decisions_path),
                    "--decision-import-report-output",
                    str(import_report_path),
                    "--missing-image-recovery-output",
                    str(recovery_report_path),
                    "--missing-image-recovery-md-output",
                    str(recovery_markdown_path),
                    "--receipt-root",
                    str(temp_path / "images"),
                    "--pipeline-report-output",
                    str(pipeline_report_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("blocked_invalid_decisions", result.stdout)
            pipeline_report = json.loads(pipeline_report_path.read_text(encoding="utf-8"))
            self.assertEqual(pipeline_report["status"], "blocked_invalid_decisions")
            self.assertIn("missing_image_recovery", pipeline_report["summary"])
            self.assertTrue(recovery_report_path.exists())

            schema = json.loads(
                (ROOT / "data" / "schemas" / "roadview_visual_review_pipeline_report.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(pipeline_report)), [])

    def test_visual_review_pipeline_cli_runs_pending_real_fixture_to_temp_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            recovery_report_path = temp_path / "recovery_report.json"
            recovery_markdown_path = temp_path / "recovery_report.md"
            operations_web_path = temp_path / "operations.web.json"
            action_plan_path = temp_path / "service_launch_action_plan.json"
            action_plan_md_path = temp_path / "service_launch_action_plan.md"
            action_plan_web_path = temp_path / "service_launch_action_plan.web.json"
            preflight_path = temp_path / "service_preflight.json"
            preflight_md_path = temp_path / "service_preflight.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_roadview_visual_review_pipeline.py"),
                    "--visual-review-sheet-output",
                    str(temp_path / "visual_sheet.json"),
                    "--decision-import-report-output",
                    str(temp_path / "decision_import.json"),
                    "--roadview-image-review-output",
                    str(temp_path / "image_review.json"),
                    "--visual-apply-report-output",
                    str(temp_path / "visual_apply.json"),
                    "--promotion-readiness-output",
                    str(temp_path / "promotion_readiness.json"),
                    "--active-candidates-output",
                    str(temp_path / "active_candidates.json"),
                    "--active-candidate-report-output",
                    str(temp_path / "active_candidate_report.json"),
                    "--gate-status-output",
                    str(temp_path / "gate_status.json"),
                    "--data-request-tracker-output",
                    str(temp_path / "tracker.json"),
                    "--data-request-tracker-csv-output",
                    str(temp_path / "tracker.csv"),
                    "--operations-readiness-output",
                    str(temp_path / "operations.json"),
                    "--missing-image-recovery-output",
                    str(recovery_report_path),
                    "--missing-image-recovery-md-output",
                    str(recovery_markdown_path),
                    "--receipt-root",
                    str(temp_path / "images"),
                    "--operations-readiness-web-output",
                    str(operations_web_path),
                    "--service-launch-action-plan-output",
                    str(action_plan_path),
                    "--service-launch-action-plan-md-output",
                    str(action_plan_md_path),
                    "--service-launch-action-plan-web-output",
                    str(action_plan_web_path),
                    "--service-preflight-output",
                    str(preflight_path),
                    "--service-preflight-md-output",
                    str(preflight_md_path),
                    "--visual-review-board-output",
                    str(temp_path / "board.html"),
                    "--pipeline-report-output",
                    str(temp_path / "pipeline_report.json"),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("status:completed", result.stdout)
            pipeline_report = json.loads((temp_path / "pipeline_report.json").read_text(encoding="utf-8"))
            self.assertEqual(pipeline_report["status"], "completed")
            self.assertEqual(pipeline_report["summary"]["decision_import"]["applied"], 0)
            self.assertEqual(pipeline_report["summary"]["missing_image_recovery"]["expected_recovery_images"], 70)
            self.assertIn("service_launch_action_plan", pipeline_report["summary"])
            self.assertIn("service_launch_action_plan_web", pipeline_report["outputs"])
            self.assertIn("service_preflight", pipeline_report["summary"])
            self.assertIn("service_preflight", pipeline_report["outputs"])
            self.assertTrue(recovery_report_path.exists())
            self.assertTrue(operations_web_path.exists())
            self.assertTrue(action_plan_web_path.exists())
            self.assertTrue(preflight_path.exists())


if __name__ == "__main__":
    unittest.main()
