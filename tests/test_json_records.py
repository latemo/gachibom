import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.json_records import extract_records, flatten_record


ROOT = Path(__file__).resolve().parents[1]


class JsonRecordTests(unittest.TestCase):
    def test_extract_records_auto_detects_nested_public_api_items(self):
        payload = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [
                            {"contentsid": "a", "title": "제주문학관"},
                            {"contentsid": "b", "title": "우유부단 카페"},
                        ]
                    }
                },
            }
        }

        records = extract_records(payload)
        self.assertEqual([record["title"] for record in records], ["제주문학관", "우유부단 카페"])

    def test_extract_records_prefers_top_level_items_over_page_metadata(self):
        payload = {
            "currentPage": 1,
            "pageSize": 10,
            "totalCount": 2,
            "result": "200",
            "items": [
                {"contentsid": "a", "title": "제주문학관"},
                {"contentsid": "b", "title": "우유부단 카페"},
            ],
        }

        records = extract_records(payload)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["contentsid"], "a")

    def test_flatten_record_preserves_nested_visitjeju_category_label(self):
        row = flatten_record(
            {
                "contentsid": "CNTS_1",
                "title": "테스트 관광지",
                "contentscd": {"value": "c1", "label": "박물관"},
                "region2cd": {"label": "제주시"},
            }
        )

        self.assertEqual(row["contentsid"], "CNTS_1")
        self.assertEqual(row["contentscdlabel"], "박물관")
        self.assertEqual(row["region2cdlabel"], "제주시")

    def test_import_place_catalog_json_cli_writes_json(self):
        payload = {
            "response": {
                "body": {
                    "items": [
                        {
                            "contentsid": "CNTS_UYUBUDAN",
                            "title": "우유부단 카페",
                            "contentscd": {"label": "카페"},
                            "roadaddress": "제주특별자치도 제주시 한림읍 금악리",
                            "phoneno": "064-000-0000",
                            "alltag": "목장,디저트",
                            "introduction": "성이시돌 목장 내 카페",
                        }
                    ]
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "payload.json"
            output_path = temp_path / "catalog.json"
            raw_path = temp_path / "raw.json"
            input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "import_place_catalog_json.py"),
                    "--input-json",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--raw-output",
                    str(raw_path),
                    "--source-name",
                    "제주관광공사",
                    "--source-url",
                    "https://www.data.go.kr/data/15076361/openapi.do",
                    "--dataset-name",
                    "비짓제주 관광정보 오픈 API",
                    "--license",
                    "이용허락범위 제한 없음",
                    "--source-updated-at",
                    "2026-06-23",
                    "--accessibility-cards",
                    str(ROOT / "data" / "jeju_accessible_spots.json"),
                    "--imported-at",
                    "2026-07-07",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            items = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(items[0]["category"], "cafe")
            self.assertEqual(items[0]["matching"]["accessibility_card_id"], "jeju_cafe_uyubudan_041")
            self.assertTrue(raw_path.exists())
            self.assertIn("summary=records:1", result.stdout)


if __name__ == "__main__":
    unittest.main()
