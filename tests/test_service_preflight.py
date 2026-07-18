import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.service_preflight import (
    build_service_preflight_report,
    render_service_preflight_markdown,
    secret_exposure_section,
)


ROOT = Path(__file__).resolve().parents[1]


class ServicePreflightTests(unittest.TestCase):
    def test_build_service_preflight_report_matches_schema_and_hides_secret(self):
        report = build_service_preflight_report(
            workspace_root=ROOT,
            generated_at=date(2026, 7, 9),
            env={
                "OPENAI_API_KEY": "sk-test-secret-that-must-not-appear",
                "OPENAI_MODEL": "gpt-5-mini",
                "KAKAO_MOBILITY_REST_API_KEY": "kakao-test-secret-that-must-not-appear",
            },
        )

        self.assertEqual(report["overall_status"], "block")
        self.assertGreater(report["summary"]["total_checks"], 0)
        self.assertTrue(any(check["check_id"] == "openai_api_key_configured" for check in report["sections"][0]["checks"]))
        kakao_key_check = next(
            check
            for check in report["sections"][0]["checks"]
            if check["check_id"] == "kakao_route_api_key_configured"
        )
        self.assertEqual(kakao_key_check["actual"], "configured")
        map_location_section = next(section for section in report["sections"] if section["name"] == "map_location")
        self.assertEqual(map_location_section["status"], "pass")
        self.assertTrue(any(check["check_id"] == "app_seed_route_locations" for check in map_location_section["checks"]))
        api_contract_section = next(section for section in report["sections"] if section["name"] == "api_contract")
        self.assertEqual(api_contract_section["status"], "pass")
        self.assertTrue(any(check["check_id"] == "api_contract_tests" for check in api_contract_section["checks"]))
        self.assertNotIn("sk-test-secret-that-must-not-appear", json.dumps(report, ensure_ascii=False))
        self.assertNotIn("kakao-test-secret-that-must-not-appear", json.dumps(report, ensure_ascii=False))

        schema = json.loads(
            (ROOT / "data" / "schemas" / "service_preflight_report.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])

    def test_service_preflight_markdown_is_operator_readable(self):
        report = build_service_preflight_report(
            workspace_root=ROOT,
            generated_at=date(2026, 7, 9),
            env={"OPENAI_API_KEY": "configured", "OPENAI_MODEL": "gpt-5-mini"},
        )

        markdown = render_service_preflight_markdown(report)

        self.assertIn("제주의마음 서비스 사전점검 리포트", markdown)
        self.assertIn("비밀값 정책", markdown)
        self.assertIn("중앙 지도 위치 계약", markdown)
        self.assertIn("추천 API 계약", markdown)
        self.assertIn("상용 공개 게이트", markdown)

    def test_secret_exposure_check_blocks_committed_kakao_key_literal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            web_dir = root / "web"
            web_dir.mkdir()
            (web_dir / "config.js").write_text(
                "KAKAO_MOBILITY_REST_API_KEY=abcdef0123456789abcdef0123456789\n",
                encoding="utf-8",
            )

            result = secret_exposure_section(root)

        self.assertEqual(result["status"], "block")
        self.assertEqual(result["checks"][0]["actual"], "1개 의심 파일")

    def test_service_preflight_cli_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "preflight.json"
            markdown_path = temp_path / "preflight.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_service_preflight_report.py"),
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(output_path),
                    "--output-md",
                    str(markdown_path),
                    "--generated-at",
                    "2026-07-09",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("service_preflight_report_output", result.stdout)
            self.assertTrue(output_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertIn("secret_policy", json.loads(output_path.read_text(encoding="utf-8")))
            self.assertIn("서비스 사전점검", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
