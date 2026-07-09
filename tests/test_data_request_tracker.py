import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.data_request_tracker import (
    build_data_request_tracker,
    export_data_request_tracker_csv,
)


ROOT = Path(__file__).resolve().parents[1]


class DataRequestTrackerTests(unittest.TestCase):
    def test_build_data_request_tracker_marks_image_request_ready_to_submit(self):
        acquisition_request = {
            "generated_at": "2026-07-08",
            "source_dataset": {"expected_full_dataset_image_count": 4748},
            "summary": {
                "total_requested_images": 2,
                "priority_sample_images": 1,
            },
        }
        receipt_report = {
            "generated_at": "2026-07-08",
            "summary": {
                "expected_images": 2,
                "received_requested_images": 0,
                "missing_requested_images": 2,
            },
        }
        gate_status = {
            "generated_at": "2026-07-08",
            "summary": {"blocked_count": 1},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "docs").mkdir()
            (temp_path / "data").mkdir()
            (temp_path / "docs" / "roadview_image_data_request_message.md").write_text("request", encoding="utf-8")
            (temp_path / "data" / "roadview_image_acquisition_priority_samples.csv").write_text(
                "image_file_name\nseed-001\n",
                encoding="utf-8",
            )
            (temp_path / "data" / "roadview_image_acquisition_full_request.csv").write_text(
                "image_file_name\nseed-001\nseed-002\n",
                encoding="utf-8",
            )
            (temp_path / "data" / "roadview_image_acquisition_place_summary.csv").write_text(
                "place_id\nseed\n",
                encoding="utf-8",
            )
            (temp_path / "data" / "roadview_image_receipt_report.json").write_text("{}", encoding="utf-8")
            (temp_path / "data" / "roadview_image_metadata.json").write_text("[]", encoding="utf-8")
            (temp_path / "data" / "place_catalog.roadview_facility.json").write_text("[]", encoding="utf-8")

            tracker = build_data_request_tracker(
                acquisition_request=acquisition_request,
                receipt_report=receipt_report,
                service_seed_gate_status=gate_status,
                generated_at=date(2026, 7, 8),
                workspace_root=temp_path,
            )

        image_item = next(item for item in tracker["items"] if item["source_id"] == "roadview_image_files")
        api_item = next(item for item in tracker["items"] if item["source_id"] == "roadview_api")
        self.assertEqual(tracker["summary"]["total_sources"], 5)
        self.assertEqual(image_item["request_status"], "ready_to_submit")
        self.assertEqual(api_item["acquisition_mode"], "direct_public_api")
        self.assertEqual(api_item["request_status"], "not_required_ready")
        self.assertEqual(image_item["current_counts"]["missing_requested_images"], 2)
        self.assertIn("공공데이터포털", image_item["next_action"])

        schema = json.loads((ROOT / "data" / "schemas" / "data_request_tracker.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(tracker)), [])

    def test_build_data_request_tracker_marks_partial_receipt_awaiting_receipt(self):
        acquisition_request = {
            "generated_at": "2026-07-08",
            "source_dataset": {"expected_full_dataset_image_count": 4748},
            "summary": {
                "total_requested_images": 1023,
                "priority_sample_images": 102,
            },
        }
        receipt_report = {
            "generated_at": "2026-07-08",
            "summary": {
                "expected_images": 1023,
                "received_requested_images": 953,
                "missing_requested_images": 70,
            },
        }
        gate_status = {
            "generated_at": "2026-07-08",
            "summary": {"blocked_count": 17},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "docs").mkdir()
            (temp_path / "data").mkdir()
            (temp_path / "docs" / "roadview_image_data_request_message.md").write_text("request", encoding="utf-8")
            (temp_path / "data" / "roadview_image_acquisition_priority_samples.csv").write_text(
                "image_file_name\nseed-001\n",
                encoding="utf-8",
            )
            (temp_path / "data" / "roadview_image_acquisition_full_request.csv").write_text(
                "image_file_name\nseed-001\n",
                encoding="utf-8",
            )
            (temp_path / "data" / "roadview_image_acquisition_place_summary.csv").write_text(
                "place_id\nseed\n",
                encoding="utf-8",
            )
            (temp_path / "data" / "roadview_image_receipt_report.json").write_text("{}", encoding="utf-8")
            (temp_path / "data" / "roadview_image_metadata.json").write_text("[]", encoding="utf-8")
            (temp_path / "data" / "place_catalog.roadview_facility.json").write_text("[]", encoding="utf-8")

            tracker = build_data_request_tracker(
                acquisition_request=acquisition_request,
                receipt_report=receipt_report,
                service_seed_gate_status=gate_status,
                generated_at=date(2026, 7, 8),
                workspace_root=temp_path,
            )

        image_item = next(item for item in tracker["items"] if item["source_id"] == "roadview_image_files")
        self.assertEqual(image_item["request_status"], "awaiting_receipt")
        self.assertEqual(image_item["current_counts"]["received_requested_images"], 953)
        self.assertIn("누락 원본 이미지", image_item["next_action"])

    def test_export_data_request_tracker_csv_writes_rows(self):
        tracker = {
            "items": [
                {
                    "source_id": "roadview_image_files",
                    "dataset_name": "이미지",
                    "provider": "제주특별자치도",
                    "portal_url": "https://www.data.go.kr/data/15110209/fileData.do",
                    "source_type": "image_files",
                    "acquisition_mode": "application_required",
                    "request_status": "ready_to_submit",
                    "gate_status": "fail",
                    "blocking_reason": "요청 이미지 2장 미수령",
                    "next_action": "요청",
                    "current_counts": {
                        "requested_images": 2,
                        "received_requested_images": 0,
                        "missing_requested_images": 2,
                    },
                    "service_usage": "시각 검수",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "tracker.csv"
            summary = export_data_request_tracker_csv(tracker, output_path)
            with output_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(summary, {"rows": 1})
        self.assertEqual(rows[0]["source_id"], "roadview_image_files")
        self.assertEqual(rows[0]["missing_requested_images"], "2")

    def test_build_data_request_tracker_cli_writes_json_and_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            acquisition_path = temp_path / "acquisition.json"
            receipt_path = temp_path / "receipt.json"
            gate_path = temp_path / "gate.json"
            output_path = temp_path / "tracker.json"
            csv_path = temp_path / "tracker.csv"
            acquisition_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-08",
                        "source_dataset": {"expected_full_dataset_image_count": 4748},
                        "summary": {"total_requested_images": 2, "priority_sample_images": 1},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            receipt_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-08",
                        "summary": {
                            "expected_images": 2,
                            "received_requested_images": 0,
                            "missing_requested_images": 2,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            gate_path.write_text(
                json.dumps({"generated_at": "2026-07-08", "summary": {"blocked_count": 1}}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_data_request_tracker.py"),
                    "--acquisition-request",
                    str(acquisition_path),
                    "--receipt-report",
                    str(receipt_path),
                    "--service-seed-gate-status",
                    str(gate_path),
                    "--output",
                    str(output_path),
                    "--csv-output",
                    str(csv_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("sources:5", result.stdout)
            self.assertTrue(output_path.exists())
            self.assertTrue(csv_path.exists())


if __name__ == "__main__":
    unittest.main()
