import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.roadview_data import facility_rows_to_accessibility_cards, infer_basic_category, metadata_rows_to_records


ROOT = Path(__file__).resolve().parents[1]


class RoadviewDataTests(unittest.TestCase):
    def test_infer_basic_category_avoids_single_syllable_false_positives(self):
        self.assertEqual(infer_basic_category("신산공원"), "rest_area")
        self.assertEqual(infer_basic_category("용연구름다리산책로"), "rest_area")
        self.assertEqual(infer_basic_category("제주세계자연유산센터"), "indoor")
        self.assertEqual(infer_basic_category("제주항일기념관"), "indoor")
        self.assertEqual(infer_basic_category("도두사수항"), "sea")
        self.assertEqual(infer_basic_category("삼성혈"), "culture")
        self.assertEqual(infer_basic_category("제주미래교육연구원과학탐구체험관"), "experience")

    def test_facility_status_rows_create_accessibility_card_drafts(self):
        rows = [
            {
                "SEQ": "1",
                "TOURIST_NM": "제주문학관",
                "TOURIST_EN": "Jeju Literature Museum",
                "TOURIST_ADDR": "제주특별자치도 제주시 연북로 339",
                "TOURIST_TEL": "064-710-3490",
                "TOURIST_DTOIL": "1",
                "TOURIST_DPARK": "2",
                "TOURIST_LNET": "Y",
                "TOURIST_NURSING": "N",
                "TOURIST_REST": "Y",
            }
        ]

        cards = facility_rows_to_accessibility_cards(rows, checked_at=date(2026, 7, 7))

        self.assertEqual(cards[0]["name"], "제주문학관")
        self.assertEqual(cards[0]["region"], "제주시")
        self.assertEqual(cards[0]["category"], "indoor")
        self.assertEqual(cards[0]["accessibility"]["accessible_toilet"]["state"], "yes")
        self.assertEqual(cards[0]["accessibility"]["parking"]["state"], "yes")
        self.assertEqual(cards[0]["accessibility"]["rental_or_assistance"]["state"], "yes")
        self.assertIn("surface_condition", cards[0]["verification"]["missing_fields"])

        schema = json.loads((ROOT / "data" / "schemas" / "accessibility_place_card.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(cards[0])), [])

    def test_metadata_rows_create_schema_valid_records(self):
        rows = [
            {
                "TOURIST_NM": "제주문학관",
                "TOURIST_EN": "Jeju Literature Museum",
                "IMG_FILE_NM": "jeju_literature_0001.jpg",
                "IMG_MK_DATE": "2022-10-01",
                "IMG_MK_TIME": "10:30",
                "LAT": "33; 27; 11.8600",
                "LON": "126; 37; 9.0300",
                "RESOLUTION": "4096*2048",
            }
        ]

        records = metadata_rows_to_records(rows)

        self.assertEqual(records[0]["tourist_name"], "제주문학관")
        self.assertEqual(records[0]["captured_at"], "2022-10-01 10:30")
        self.assertAlmostEqual(records[0]["latitude"], 33.45329444444444)
        self.assertAlmostEqual(records[0]["longitude"], 126.619175)

        schema = json.loads((ROOT / "data" / "schemas" / "roadview_image_metadata.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(records[0])), [])

    def test_roadview_facility_cli_writes_cards_and_catalog(self):
        csv_content = (
            "SEQ,TOURIST_NM,TOURIST_EN,TOURIST_ADDR,TOURIST_TEL,TOURIST_DTOIL,TOURIST_DPARK,TOURIST_LNET,TOURIST_NURSING,TOURIST_REST\n"
            "1,제주문학관,Jeju Literature Museum,제주특별자치도 제주시 연북로 339,064-710-3490,1,2,Y,N,Y\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "facility.csv"
            cards_path = temp_path / "cards.json"
            catalog_path = temp_path / "catalog.json"
            input_path.write_text(csv_content, encoding="utf-8-sig")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "import_roadview_facility_cards.py"),
                    "--input",
                    str(input_path),
                    "--output-cards",
                    str(cards_path),
                    "--output-catalog",
                    str(catalog_path),
                    "--accessibility-cards",
                    str(ROOT / "data" / "jeju_accessible_spots.json"),
                    "--checked-at",
                    "2026-07-07",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("cards_imported=1", result.stdout)
            self.assertIn("catalog_summary=imported:1", result.stdout)
            self.assertEqual(json.loads(cards_path.read_text(encoding="utf-8"))[0]["name"], "제주문학관")
            catalog_item = json.loads(catalog_path.read_text(encoding="utf-8"))[0]
            self.assertEqual(catalog_item["name"], "제주문학관")
            self.assertEqual(catalog_item["category"], "indoor")

    def test_roadview_metadata_cli_writes_json(self):
        csv_content = (
            "TOURIST_NM,TOURIST_EN,IMG_FILE_NM,IMG_MK_DATE,IMG_MK_TIME,LAT,LON,RESOLUTION\n"
            "제주문학관,Jeju Literature Museum,jeju_literature_0001.jpg,2022-10-01,10:30,33.482,126.531,4096*2048\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "metadata.csv"
            output_path = temp_path / "metadata.json"
            input_path.write_text(csv_content, encoding="utf-8-sig")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "import_roadview_metadata.py"),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("metadata_imported=1", result.stdout)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))[0]["image_file_name"], "jeju_literature_0001.jpg")


if __name__ == "__main__":
    unittest.main()
