import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.roadview_image_download import (
    build_roadview_image_download_report,
    build_roadview_provider_404_image_report,
    roadview_image_url,
)


ROOT = Path(__file__).resolve().parents[1]


def sample_acquisition_request():
    return {
        "generated_at": "2026-07-08",
        "items": [
            {
                "card": {"id": "jeju_roadview_seed_001", "name": "시드후보"},
                "priority_images": [
                    {
                        "image_file_name": "SEED-1-001",
                        "request_tier": "priority_visual_review_sample",
                        "tourist_name": "시드후보",
                        "tourist_name_en": "SEED",
                        "captured_at": "2022-07-28 09:34",
                    }
                ],
                "supplemental_images": [
                    {
                        "image_file_name": "SEED-1-002",
                        "request_tier": "supplemental_place_sequence",
                        "tourist_name": "시드후보",
                        "tourist_name_en": "SEED",
                        "captured_at": "2022-07-28 09:35",
                    }
                ],
            }
        ],
    }


class RoadviewImageDownloadTests(unittest.TestCase):
    def test_roadview_image_url_uses_public_gis_image_pattern(self):
        url = roadview_image_url(
            {
                "tourist_name_en": "JEJUNATIONALMU",
                "image_file_name": "JEJUNATIONALMU-1-001",
            }
        )
        self.assertEqual(
            url,
            "https://gis.jeju.go.kr/images/roadview/JEJUNATIONALMU/JEJUNATIONALMU-1-001.jpg",
        )

    def test_build_download_report_dry_run_plans_priority_images(self):
        report = build_roadview_image_download_report(
            sample_acquisition_request(),
            target_root="data/raw/roadview_images",
            tier="priority",
            dry_run=True,
            generated_at=date(2026, 7, 8),
        )

        self.assertEqual(report["summary"]["total_items"], 1)
        self.assertEqual(report["summary"]["planned"], 1)
        self.assertEqual(report["items"][0]["status"], "planned")
        self.assertEqual(report["items"][0]["image_file_name"], "SEED-1-001")

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_image_download_report.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_failed_download_records_http_error_status(self):
        def opener(request, timeout_seconds):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

        with tempfile.TemporaryDirectory() as temp_dir:
            report = build_roadview_image_download_report(
                sample_acquisition_request(),
                target_root=Path(temp_dir) / "images",
                tier="priority",
                generated_at=date(2026, 7, 8),
                opener=opener,
            )

        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(report["items"][0]["http_status"], 404)
        self.assertIn("HTTP Error 404", report["items"][0]["error"])

    def test_build_provider_404_report_filters_source_image_404s(self):
        download_report = {
            "generated_at": "2026-07-08",
            "source_endpoint": "https://gis.jeju.go.kr/images/roadview",
            "tier": "all",
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
                    "status": "failed",
                    "http_status": 404,
                    "error": "HTTP Error 404: Not Found",
                },
                {
                    "card_id": "jeju_roadview_seed_001",
                    "place_name": "시드후보",
                    "image_file_name": "SEED-1-002",
                    "request_tier": "priority_visual_review_sample",
                    "tourist_name": "시드후보",
                    "tourist_name_en": "SEED",
                    "captured_at": "2022-07-28 09:35",
                    "source_url": "https://gis.jeju.go.kr/images/roadview/SEED/SEED-1-002.jpg",
                    "status": "failed",
                    "http_status": None,
                    "error": "timed out",
                },
            ],
        }

        report = build_roadview_provider_404_image_report(download_report, generated_at=date(2026, 7, 8))

        self.assertEqual(report["summary"]["provider_404_images"], 1)
        self.assertEqual(report["summary"]["affected_places"], 1)
        self.assertEqual(report["items"][0]["image_file_name"], "SEED-1-001")

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_provider_404_image_report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_download_cli_writes_dry_run_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            request_path = temp_path / "acquisition.json"
            output_path = temp_path / "download_report.json"
            request_path.write_text(json.dumps(sample_acquisition_request(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "download_roadview_requested_images.py"),
                    "--acquisition-request",
                    str(request_path),
                    "--output",
                    str(output_path),
                    "--target-root",
                    str(temp_path / "images"),
                    "--tier",
                    "priority",
                    "--dry-run",
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("planned:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["planned"], 1)

    def test_provider_404_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            download_report_path = temp_path / "download_report.json"
            output_path = temp_path / "provider_404.json"
            download_report_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-08",
                        "source_endpoint": "https://gis.jeju.go.kr/images/roadview",
                        "tier": "all",
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
                                "status": "failed",
                                "http_status": None,
                                "error": "HTTP Error 404: Not Found",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_provider_404_image_report.py"),
                    "--download-report",
                    str(download_report_path),
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
            self.assertIn("provider_404:1", result.stdout)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8"))["summary"]["provider_404_images"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
