import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.service_launch_actions import (
    build_service_launch_action_plan,
    render_service_launch_action_plan_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


def operations_readiness() -> dict:
    return {
        "overall_status": "blocked_for_full_service",
        "summary": {"next_action": "누락 원본 이미지 수령"},
    }


def service_seed_gate_status() -> dict:
    return {
        "overall_status": "blocked",
        "summary": {
            "total_places": 2,
            "expected_images": 10,
            "received_requested_images": 7,
            "missing_requested_images": 3,
            "expected_priority_sample_images": 12,
            "received_priority_sample_images": 12,
            "open_visual_review_places": 2,
            "verified_roadview_places": 0,
            "promoted_active_candidates": 0,
            "next_action": "누락 원본 이미지 복구",
        },
    }


def provider_404_report() -> dict:
    return {
        "summary": {
            "provider_404_images": 3,
            "affected_places": 2,
            "by_place": {"테스트 박물관": 2, "테스트 공원": 1},
        },
        "items": [
            {"place_name": "테스트 박물관", "image_file_name": "MUSEUM-1-001"},
            {"place_name": "테스트 박물관", "image_file_name": "MUSEUM-1-002"},
            {"place_name": "테스트 공원", "image_file_name": "PARK-1-001"},
        ],
        "recommended_action": "제공기관에 누락 파일 재요청",
    }


def image_receipt_report() -> dict:
    return {
        "summary": {
            "expected_images": 10,
            "received_requested_images": 7,
            "missing_requested_images": 3,
        }
    }


def visual_review_sheet() -> dict:
    field_results = [
        {"field": "entrance_step_or_ramp", "status": "pending_visual_review"},
        {"field": "main_path_slope", "status": "pending_visual_review"},
        {"field": "surface_condition", "status": "pending_visual_review"},
        {"field": "parking_to_entrance_route", "status": "pending_visual_review"},
    ]
    return {
        "summary": {
            "by_status": {"open": 2},
            "by_field_status": {"pending_visual_review": 8},
        },
        "items": [
            {
                "card": {"name": "테스트 박물관"},
                "status": "open",
                "review_decision": "pending_reviewer_input",
                "field_results": field_results,
            },
            {
                "card": {"name": "테스트 공원"},
                "status": "open",
                "review_decision": "pending_reviewer_input",
                "field_results": field_results,
            },
        ],
    }


class ServiceLaunchActionTests(unittest.TestCase):
    def test_build_service_launch_action_plan_matches_schema_and_prioritizes_blockers(self):
        plan = build_service_launch_action_plan(
            operations_readiness(),
            service_seed_gate_status(),
            provider_404_report(),
            image_receipt_report(),
            visual_review_sheet(),
            generated_at=date(2026, 7, 9),
        )

        self.assertEqual(plan["overall_status"], "blocked_for_full_service")
        self.assertEqual(plan["summary"]["missing_roadview_images"], 3)
        self.assertEqual(plan["summary"]["visual_review_open_places"], 2)
        self.assertEqual(plan["summary"]["promoted_active_candidates"], 0)
        self.assertEqual(plan["actions"][0]["status"], "blocked_external_request")
        self.assertEqual(plan["actions"][0]["affected_places"][0]["place_name"], "테스트 박물관")
        self.assertIn("누락 로드뷰 원본 이미지 3장 복구", plan["summary"]["first_action"])

        schema = json.loads(
            (ROOT / "data" / "schemas" / "service_launch_action_plan.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(plan)), [])

    def test_render_markdown_contains_human_action_plan(self):
        plan = build_service_launch_action_plan(
            operations_readiness(),
            service_seed_gate_status(),
            provider_404_report(),
            image_receipt_report(),
            visual_review_sheet(),
            generated_at=date(2026, 7, 9),
        )

        markdown = render_service_launch_action_plan_markdown(plan)

        self.assertIn("제주의마음 서비스 런칭 실행 계획", markdown)
        self.assertIn("누락 이미지 영향 장소", markdown)
        self.assertIn("테스트 박물관", markdown)
        self.assertIn("제공기관에 누락 파일 재요청", markdown)

    def test_build_service_launch_action_plan_cli_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            operations_path = temp_path / "operations.json"
            gate_path = temp_path / "gate.json"
            provider_path = temp_path / "provider_404.json"
            receipt_path = temp_path / "receipt.json"
            visual_path = temp_path / "visual.json"
            output_json = temp_path / "plan.json"
            output_md = temp_path / "plan.md"
            web_output_json = temp_path / "web_plan.json"
            operations_path.write_text(json.dumps(operations_readiness(), ensure_ascii=False), encoding="utf-8")
            gate_path.write_text(json.dumps(service_seed_gate_status(), ensure_ascii=False), encoding="utf-8")
            provider_path.write_text(json.dumps(provider_404_report(), ensure_ascii=False), encoding="utf-8")
            receipt_path.write_text(json.dumps(image_receipt_report(), ensure_ascii=False), encoding="utf-8")
            visual_path.write_text(json.dumps(visual_review_sheet(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_service_launch_action_plan.py"),
                    "--operations-readiness",
                    str(operations_path),
                    "--service-seed-gate-status",
                    str(gate_path),
                    "--provider-404-report",
                    str(provider_path),
                    "--image-receipt-report",
                    str(receipt_path),
                    "--visual-review-sheet",
                    str(visual_path),
                    "--output-json",
                    str(output_json),
                    "--output-md",
                    str(output_md),
                    "--web-output-json",
                    str(web_output_json),
                    "--generated-at",
                    "2026-07-09",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("service_launch_action_plan_web_json", result.stdout)
            self.assertEqual(json.loads(output_json.read_text(encoding="utf-8"))["summary"]["missing_roadview_images"], 3)
            self.assertEqual(
                json.loads(web_output_json.read_text(encoding="utf-8"))["summary"]["visual_review_open_places"],
                2,
            )
            self.assertIn("서비스 런칭 실행 계획", output_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
