import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.operations_readiness import build_operations_readiness_report


ROOT = Path(__file__).resolve().parents[1]


def place_card(index: int, verification_status: str = "partial") -> dict:
    return {
        "id": f"jeju_test_place_{index:03d}",
        "name": f"테스트 장소 {index}",
        "status": "active",
        "sources": [{"title": "공식 출처", "url": "https://example.com", "type": "public_agency"}],
        "safety_notes": ["방문 전 운영 여부 확인"],
        "verification": {"status": verification_status},
    }


def data_request_tracker() -> dict:
    return {
        "summary": {"ready_to_use_sources": 2, "total_sources": 4},
        "items": [
            {
                "source_id": "roadview_image_files",
                "request_status": "ready_to_submit",
                "next_action": "이미지 원본 요청",
            },
            {
                "source_id": "roadview_api",
                "request_status": "not_required_ready",
                "next_action": "API 호출 상태 확인",
            },
        ],
    }


def service_seed_gate_status() -> dict:
    return {
        "overall_status": "blocked",
        "summary": {
            "next_action": "제공기관 이미지 원본 수령",
            "missing_priority_sample_images": 102,
            "promoted_active_candidates": 0,
            "total_places": 17,
        },
    }


class OperationsReadinessTests(unittest.TestCase):
    def test_build_operations_readiness_report_blocks_full_service_on_image_dependency(self):
        cards = [place_card(index) for index in range(1, 31)]

        report = build_operations_readiness_report(
            cards,
            data_request_tracker(),
            service_seed_gate_status(),
            generated_at=date(2026, 7, 8),
            workspace_root=ROOT,
        )

        self.assertEqual(report["overall_status"], "blocked_for_full_service")
        self.assertGreater(report["summary"]["blocker_checks"], 0)
        self.assertIn("이미지 원본 요청", report["summary"]["next_action"])
        self.assertTrue(any(check["check_id"] == "roadview_image_request_submission" for check in report["blockers"]))

        schema = json.loads(
            (ROOT / "data" / "schemas" / "operations_readiness_report.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_build_operations_readiness_report_cli_writes_report(self):
        cards = [place_card(index) for index in range(1, 31)]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cards_path = temp_path / "cards.json"
            tracker_path = temp_path / "tracker.json"
            gate_path = temp_path / "gate.json"
            output_path = temp_path / "operations_readiness.json"
            web_output_path = temp_path / "web_operations_readiness.json"
            cards_path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
            tracker_path.write_text(json.dumps(data_request_tracker(), ensure_ascii=False), encoding="utf-8")
            gate_path.write_text(json.dumps(service_seed_gate_status(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_operations_readiness_report.py"),
                    "--place-cards",
                    str(cards_path),
                    "--data-request-tracker",
                    str(tracker_path),
                    "--service-seed-gate-status",
                    str(gate_path),
                    "--output",
                    str(output_path),
                    "--web-output",
                    str(web_output_path),
                    "--generated-at",
                    "2026-07-08",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("blocked_for_full_service", result.stdout)
            self.assertIn("operations_readiness_report_web_output", result.stdout)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8"))["overall_status"],
                "blocked_for_full_service",
            )
            self.assertEqual(
                json.loads(web_output_path.read_text(encoding="utf-8"))["overall_status"],
                "blocked_for_full_service",
            )


if __name__ == "__main__":
    unittest.main()
