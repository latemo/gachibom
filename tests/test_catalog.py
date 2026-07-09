import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.catalog import import_catalog_csv, summarize_catalog


ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_import_catalog_csv_matches_accessibility_cards(self):
        cards = json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))
        items = import_catalog_csv(
            ROOT / "data" / "templates" / "place_catalog.template.csv",
            imported_at=date(2026, 7, 7),
            accessibility_cards=cards,
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["matching"]["match_status"], "matched")
        self.assertEqual(items[0]["matching"]["accessibility_card_id"], "jeju_indoor_literature_022")
        self.assertEqual(items[1]["category"], "food_market")

    def test_imported_catalog_items_match_schema(self):
        cards = json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))
        items = import_catalog_csv(
            ROOT / "data" / "templates" / "place_catalog.template.csv",
            imported_at=date(2026, 7, 7),
            accessibility_cards=cards,
        )
        schema = json.loads((ROOT / "data" / "schemas" / "place_catalog.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for item in items:
            self.assertEqual(list(validator.iter_errors(item)), [])

    def test_summarize_catalog(self):
        cards = json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))
        items = import_catalog_csv(
            ROOT / "data" / "templates" / "place_catalog.template.csv",
            imported_at=date(2026, 7, 7),
            accessibility_cards=cards,
        )
        summary = summarize_catalog(items)
        self.assertEqual(summary.imported, 2)
        self.assertEqual(summary.matched, 2)

    def test_unknown_place_stays_unmatched(self):
        content = (
            "name,category,region,address,phone,homepage,latitude,longitude,tags,description,"
            "source_name,source_url,dataset_name,license,source_updated_at,raw_category,raw_id\n"
            "없는 장소,음식점,제주시,제주시 어딘가,,,,,,테스트,,운영자 샘플,https://example.com,sample,sample,2026-07-07,음식점,x\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            items = import_catalog_csv(temp_path, imported_at=date(2026, 7, 7), accessibility_cards=[])
            self.assertEqual(items[0]["matching"]["match_status"], "unmatched")
            self.assertEqual(items[0]["category"], "restaurant")
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
