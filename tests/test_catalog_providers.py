import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.catalog import import_catalog_rows
from src.catalog_providers import SourceDefaults, normalize_public_place_rows


ROOT = Path(__file__).resolve().parents[1]


class CatalogProviderTests(unittest.TestCase):
    def test_normalizes_korean_public_dataset_headers(self):
        cards = json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))
        source = SourceDefaults(
            source_name="제주관광공사",
            source_url="https://www.data.go.kr/data/15076361/openapi.do",
            dataset_name="비짓제주 관광정보 오픈 API",
            license="이용허락범위 제한 없음",
            source_updated_at="2026-06-23",
        )
        rows = normalize_public_place_rows(
            [
                {
                    "콘텐츠명": "우유부단 카페",
                    "콘텐츠분류": "카페",
                    "주소": "제주특별자치도 제주시 한림읍 금악리",
                    "전화번호": "064-000-0000",
                    "홈페이지": "https://example.com",
                    "위도": "33.347",
                    "경도": "126.305",
                    "키워드": "목장,디저트",
                    "소개": "성이시돌 목장 내 카페",
                    "예약가능여부": "Y",
                    "대표메뉴기타": "우유 아이스크림",
                    "콘텐츠아이디": "visitjeju-uyubudan",
                }
            ],
            source_defaults=source,
        )

        self.assertEqual(rows[0]["name"], "우유부단 카페")
        self.assertEqual(rows[0]["category"], "cafe")
        self.assertEqual(rows[0]["region"], "제주시")
        self.assertIn("예약가능", rows[0]["tags"])
        self.assertIn("대표메뉴", rows[0]["description"])

        items = import_catalog_rows(rows, imported_at=date(2026, 7, 7), accessibility_cards=cards)
        self.assertEqual(items[0]["matching"]["match_status"], "matched")
        self.assertEqual(items[0]["matching"]["accessibility_card_id"], "jeju_cafe_uyubudan_041")

    def test_default_category_handles_restaurant_content_exports(self):
        source = SourceDefaults(
            source_name="제주관광공사",
            source_url="https://www.data.go.kr/data/15041984/fileData.do",
            dataset_name="제주관광정보시스템(VISIT JEJU)_음식점콘텐츠",
            license="이용허락범위 제한 없음",
            source_updated_at="2026-03-11",
        )
        rows = normalize_public_place_rows(
            [{"콘텐츠명": "테스트 식당", "대표메뉴기타": "전복죽", "예약가능여부": "가능"}],
            source_defaults=source,
            default_category="restaurant",
        )

        self.assertEqual(rows[0]["category"], "restaurant")
        self.assertEqual(rows[0]["raw_category"], "restaurant")
        self.assertIn("예약가능", rows[0]["tags"])
        self.assertIn("전복죽", rows[0]["description"])

        items = import_catalog_rows(rows, imported_at=date(2026, 7, 7), accessibility_cards=[])
        schema = json.loads((ROOT / "data" / "schemas" / "place_catalog.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(items[0])), [])

    def test_default_other_does_not_block_name_based_category_inference(self):
        source = SourceDefaults(
            source_name="제주특별자치도",
            source_url="https://www.data.go.kr/data/15109153/fileData.do",
            dataset_name="사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
            license="이용허락범위 제한 없음",
            source_updated_at="2025-07-30",
        )
        rows = normalize_public_place_rows(
            [{"관광지명": "제주문학관", "관광지 주소": "제주특별자치도 제주시 연북로 339"}],
            source_defaults=source,
            default_category="other",
        )

        self.assertEqual(rows[0]["category"], "indoor")
        self.assertEqual(rows[0]["raw_category"], "indoor")

    def test_category_inference_avoids_single_syllable_false_positives(self):
        self.assertEqual(normalize_public_place_rows(
            [{"관광지명": "신산공원"}],
            source_defaults=SourceDefaults(
                source_name="제주특별자치도",
                source_url="https://www.data.go.kr/data/15109153/fileData.do",
                dataset_name="사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
            ),
            default_category="other",
        )[0]["category"], "rest_area")
        self.assertEqual(normalize_public_place_rows(
            [{"관광지명": "제주세계자연유산센터"}],
            source_defaults=SourceDefaults(
                source_name="제주특별자치도",
                source_url="https://www.data.go.kr/data/15109153/fileData.do",
                dataset_name="사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
            ),
            default_category="other",
        )[0]["category"], "indoor")
        self.assertEqual(normalize_public_place_rows(
            [{"관광지명": "제주항일기념관"}],
            source_defaults=SourceDefaults(
                source_name="제주특별자치도",
                source_url="https://www.data.go.kr/data/15109153/fileData.do",
                dataset_name="사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
            ),
            default_category="other",
        )[0]["category"], "indoor")
        self.assertEqual(normalize_public_place_rows(
            [{"관광지명": "삼성혈"}],
            source_defaults=SourceDefaults(
                source_name="제주특별자치도",
                source_url="https://www.data.go.kr/data/15109153/fileData.do",
                dataset_name="사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
            ),
            default_category="other",
        )[0]["category"], "culture")
        self.assertEqual(normalize_public_place_rows(
            [{"관광지명": "제주미래교육연구원과학탐구체험관"}],
            source_defaults=SourceDefaults(
                source_name="제주특별자치도",
                source_url="https://www.data.go.kr/data/15109153/fileData.do",
                dataset_name="사회적약자 시설 데이터(로드뷰) 구축 관광지 현황",
            ),
            default_category="other",
        )[0]["category"], "experience")

    def test_import_place_catalog_cli_writes_json(self):
        csv_content = (
            "콘텐츠명,콘텐츠분류,주소,키워드\n"
            "우유부단 카페,카페,제주특별자치도 제주시 한림읍 금악리,\"목장,디저트\"\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "visitjeju.csv"
            output_path = temp_path / "catalog.json"
            input_path.write_text(csv_content, encoding="utf-8-sig")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "import_place_catalog.py"),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
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
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["category"], "cafe")
            self.assertIn("summary=imported:1", result.stdout)


if __name__ == "__main__":
    unittest.main()
