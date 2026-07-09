import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.roadview_missing_image_recovery import (
    build_roadview_missing_image_recovery_report,
    render_roadview_missing_image_recovery_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


def provider_404_report() -> dict:
    return {
        "generated_at": "2026-07-09",
        "items": [
            {
                "card_id": "place_001",
                "place_name": "테스트 박물관",
                "image_file_name": "MUSEUM-1-001",
                "request_tier": "supplemental_place_sequence",
                "tourist_name": "테스트 박물관",
                "tourist_name_en": "MUSEUM",
                "captured_at": "2022-08-01 10:00",
                "source_url": "https://example.com/MUSEUM-1-001.jpg",
                "error": "HTTP Error 404: Not Found",
            },
            {
                "card_id": "place_001",
                "place_name": "테스트 박물관",
                "image_file_name": "MUSEUM-1-002",
                "request_tier": "supplemental_place_sequence",
                "tourist_name": "테스트 박물관",
                "tourist_name_en": "MUSEUM",
                "captured_at": "2022-08-01 10:01",
                "source_url": "https://example.com/MUSEUM-1-002.jpg",
                "error": "HTTP Error 404: Not Found",
            },
            {
                "card_id": "place_002",
                "place_name": "테스트 공원",
                "image_file_name": "PARK-1-001",
                "request_tier": "supplemental_place_sequence",
                "tourist_name": "테스트 공원",
                "tourist_name_en": "PARK",
                "captured_at": "2022-08-01 11:00",
                "source_url": "https://example.com/PARK-1-001.jpg",
                "error": "HTTP Error 404: Not Found",
            },
        ],
    }


class RoadviewMissingImageRecoveryTests(unittest.TestCase):
    def test_recovery_report_tracks_recovered_missing_and_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt_root = Path(temp_dir)
            (receipt_root / "MUSEUM-1-001.jpg").write_bytes(b"image")

            report = build_roadview_missing_image_recovery_report(
                provider_404_report(),
                receipt_root=receipt_root,
                generated_at=date(2026, 7, 9),
            )

        self.assertEqual(report["overall_status"], "partial_recovery")
        self.assertEqual(report["summary"]["expected_recovery_images"], 3)
        self.assertEqual(report["summary"]["recovered_images"], 1)
        self.assertEqual(report["summary"]["still_missing_images"], 2)
        self.assertEqual(report["items"][0]["status"], "recovered")
        self.assertEqual(report["items"][0]["sha256"], hashlib.sha256(b"image").hexdigest())

        schema = json.loads(
            (ROOT / "data" / "schemas" / "roadview_missing_image_recovery_report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_recovery_report_detects_duplicate_file_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt_root = Path(temp_dir)
            (receipt_root / "MUSEUM-1-001.jpg").write_bytes(b"first")
            nested = receipt_root / "nested"
            nested.mkdir()
            (nested / "MUSEUM-1-001.png").write_bytes(b"second")

            report = build_roadview_missing_image_recovery_report(
                provider_404_report(),
                receipt_root=receipt_root,
                generated_at=date(2026, 7, 9),
                hash_files=False,
            )

        self.assertEqual(report["overall_status"], "needs_duplicate_resolution")
        self.assertEqual(report["summary"]["duplicate_name_images"], 1)
        self.assertEqual(report["items"][0]["status"], "duplicate_name")
        self.assertEqual(len(report["items"][0]["duplicate_candidate_paths"]), 2)

    def test_markdown_is_operator_readable(self):
        report = build_roadview_missing_image_recovery_report(
            provider_404_report(),
            receipt_root=Path("missing-root"),
            generated_at=date(2026, 7, 9),
            hash_files=False,
        )

        markdown = render_roadview_missing_image_recovery_markdown(report)

        self.assertIn("로드뷰 누락 원본 이미지 회복 검증 리포트", markdown)
        self.assertIn("아직 누락: 3장", markdown)
        self.assertIn("테스트 박물관", markdown)

    def test_recovery_report_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            provider_path = temp_path / "provider_404.json"
            receipt_root = temp_path / "images"
            output_path = temp_path / "recovery.json"
            markdown_path = temp_path / "recovery.md"
            receipt_root.mkdir()
            (receipt_root / "PARK-1-001.jpg").write_bytes(b"park")
            provider_path.write_text(json.dumps(provider_404_report(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_roadview_missing_image_recovery_report.py"),
                    "--provider-404-report",
                    str(provider_path),
                    "--receipt-root",
                    str(receipt_root),
                    "--output",
                    str(output_path),
                    "--output-md",
                    str(markdown_path),
                    "--generated-at",
                    "2026-07-09",
                    "--skip-hash",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("recovered:1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["recovered_images"], 1)
            self.assertIn("회복 확인: 1장", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
