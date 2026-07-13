import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from src.place_visit_info import (
    build_reviewed_visit_info_index,
    build_visit_info_index,
    empty_visit_info,
    enrich_places_with_visit_info,
    visit_info_for_place,
)


ROOT = Path(__file__).resolve().parents[1]


def catalog_row(
    *,
    spot_id="jeju_indoor_literature_022",
    match_status="matched",
    confidence=1.0,
    status="active",
    address="제주특별자치도 제주시 연북로 339",
    phone="064-710-3490",
    source_url="https://www.data.go.kr/data/example",
    updated_at="2025-07-30",
    catalog_id="catalog_indoor_00000001",
):
    return {
        "catalog_id": catalog_id,
        "name": "제주문학관",
        "address": address,
        "phone": phone,
        "homepage": "https://example.invalid/not-an-official-site",
        "status": status,
        "matching": {
            "accessibility_card_id": spot_id,
            "match_status": match_status,
            "match_confidence": confidence,
        },
        "source": {
            "name": "제주특별자치도",
            "dataset_name": "제주 관광지 현황",
            "url": source_url,
            "updated_at": updated_at,
        },
    }


class PlaceVisitInfoTests(unittest.TestCase):
    def test_committed_reviewed_visit_info_matches_schema_and_place_ids(self):
        rows = json.loads(
            (ROOT / "data" / "place_visit_info_overrides.json").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "data" / "schemas" / "place_visit_info_overrides.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = list(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(rows)
        )
        self.assertEqual(errors, [])

        places = json.loads(
            (ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8")
        )
        place_names = {place["id"]: place["name"] for place in places}
        self.assertEqual(len({row["spot_id"] for row in rows}), len(rows))
        self.assertTrue(all(place_names.get(row["spot_id"]) == row["name"] for row in rows))

    def test_empty_visit_info_has_fixed_shape_and_no_shared_mutable_values(self):
        first = empty_visit_info()
        second = empty_visit_info()

        self.assertEqual(
            list(first),
            [
                "address",
                "phone",
                "operating_hours",
                "official_url",
                "reservation_url",
                "service_status",
                "notice",
                "verification_status",
                "last_verified_at",
                "source_updated_at",
                "missing_fields",
                "evidence",
            ],
        )
        self.assertEqual(first["service_status"], "unknown")
        self.assertEqual(first["verification_status"], "needs_check")
        first["missing_fields"].remove("address")
        first["evidence"].append({"source_url": "https://example.com"})
        self.assertIn("address", second["missing_fields"])
        self.assertEqual(second["evidence"], [])

    def test_build_index_only_accepts_active_high_confidence_exact_matches(self):
        accepted = catalog_row()
        rows = [
            accepted,
            catalog_row(spot_id="candidate", match_status="candidate"),
            catalog_row(spot_id="low_confidence", confidence=0.98),
            catalog_row(spot_id="invalid_confidence", confidence=float("nan")),
            catalog_row(spot_id="inactive", status="hidden"),
            catalog_row(spot_id="missing_id"),
            None,
        ]
        rows[-2]["matching"]["accessibility_card_id"] = None

        index = build_visit_info_index(rows)

        self.assertEqual(list(index), ["jeju_indoor_literature_022"])
        info = index["jeju_indoor_literature_022"]
        self.assertEqual(info["address"], accepted["address"])
        self.assertEqual(info["phone"], accepted["phone"])
        self.assertIsNone(info["operating_hours"])
        self.assertIsNone(info["official_url"])
        self.assertIsNone(info["reservation_url"])
        self.assertEqual(info["service_status"], "unknown")
        self.assertEqual(info["verification_status"], "needs_check")
        self.assertIsNone(info["last_verified_at"])
        self.assertEqual(info["source_updated_at"], "2025-07-30")
        self.assertEqual(
            info["missing_fields"],
            ["operating_hours", "official_url", "reservation_url"],
        )
        self.assertEqual(
            info["evidence"][0],
            {
                "fields": ["address", "phone"],
                "status": "needs_check",
                "source_title": "제주 관광지 현황",
                "source_url": "https://www.data.go.kr/data/example",
                "source_type": "public_agency",
                "checked_at": None,
                "observed_at": None,
                "note": (
                    "공공 카탈로그 원본 갱신일은 2025-07-30이며, "
                    "실제 현장 확인일이 아니므로 방문 전 공식 정보 재확인이 필요합니다."
                ),
            },
        )

    def test_malicious_or_malformed_evidence_urls_are_not_exposed(self):
        for source_url in (
            "javascript:alert(1)",
            "data:text/html,payload",
            "https:///missing-host",
            "//example.com/no-scheme",
        ):
            with self.subTest(source_url=source_url):
                info = build_visit_info_index([catalog_row(source_url=source_url)])[
                    "jeju_indoor_literature_022"
                ]
                self.assertEqual(info["evidence"], [])
                self.assertIsNone(info["official_url"])
                self.assertIsNone(info["reservation_url"])

    def test_duplicate_selection_is_deterministic_and_prefers_newest_source(self):
        older = catalog_row(
            address="오래된 주소",
            phone="064-000-0000",
            updated_at="2024-01-01",
            catalog_id="catalog_indoor_older",
        )
        newer = catalog_row(
            address="최신 주소",
            phone="064-111-1111",
            updated_at="2026-01-15",
            catalog_id="catalog_indoor_newer",
        )

        forward = build_visit_info_index([older, newer])
        reverse = build_visit_info_index([newer, older])

        self.assertEqual(forward, reverse)
        self.assertEqual(forward["jeju_indoor_literature_022"]["address"], "최신 주소")
        self.assertIsNone(forward["jeju_indoor_literature_022"]["last_verified_at"])
        self.assertEqual(forward["jeju_indoor_literature_022"]["source_updated_at"], "2026-01-15")

    def test_enrichment_does_not_mutate_inputs_and_adds_defaults_for_unmatched_places(self):
        places = [
            {
                "id": "jeju_indoor_literature_022",
                "name": "제주문학관",
                "accessibility": {"parking": {"state": "yes"}},
            },
            {"id": "jeju_unmatched_001", "name": "매칭 없음"},
        ]
        rows = [catalog_row()]
        original_places = copy.deepcopy(places)
        original_rows = copy.deepcopy(rows)

        enriched = enrich_places_with_visit_info(places, rows)

        self.assertEqual(places, original_places)
        self.assertEqual(rows, original_rows)
        self.assertIsNot(enriched[0], places[0])
        self.assertIsNot(enriched[0]["accessibility"], places[0]["accessibility"])
        self.assertEqual(enriched[0]["visit_info"]["phone"], "064-710-3490")
        self.assertEqual(enriched[1]["visit_info"], empty_visit_info())

    def test_reviewed_information_overrides_catalog_fields_and_keeps_missing_catalog_values(self):
        reviewed = {
            "spot_id": "jeju_indoor_literature_022",
            "visit_info": {
                "address": "공식 확인 주소",
                "phone": None,
                "operating_hours": "09:00~18:00",
                "official_url": "https://official.example.com",
                "reservation_url": None,
                "service_status": "active",
                "notice": "방문 전 확인",
                "verification_status": "partial",
                "last_verified_at": "2026-07-13",
                "source_updated_at": None,
                "missing_fields": ["phone", "reservation_url"],
                "evidence": [
                    {
                        "fields": ["address", "operating_hours", "official_url", "service_status"],
                        "status": "verified",
                        "source_title": "공식 페이지",
                        "source_url": "https://official.example.com",
                        "source_type": "official",
                        "checked_at": "2026-07-13",
                        "observed_at": None,
                        "note": "공식 페이지 확인",
                    }
                ],
            },
        }

        enriched = enrich_places_with_visit_info(
            [{"id": "jeju_indoor_literature_022"}],
            [catalog_row()],
            [reviewed],
        )[0]["visit_info"]

        self.assertEqual(enriched["address"], "공식 확인 주소")
        self.assertEqual(enriched["phone"], "064-710-3490")
        self.assertEqual(enriched["operating_hours"], "09:00~18:00")
        self.assertEqual(enriched["service_status"], "active")
        self.assertEqual(enriched["verification_status"], "partial")
        self.assertEqual(enriched["last_verified_at"], "2026-07-13")
        self.assertEqual(enriched["source_updated_at"], "2025-07-30")
        self.assertEqual(len(enriched["evidence"]), 2)
        self.assertNotIn("phone", enriched["missing_fields"])

    def test_reviewed_information_without_date_or_evidence_is_ignored(self):
        base = empty_visit_info()
        without_date = copy.deepcopy(base)
        without_date["evidence"] = [
            {
                "fields": ["address"],
                "status": "verified",
                "source_title": "공식",
                "source_url": "https://example.com",
                "source_type": "official",
                "checked_at": "2026-07-13",
                "observed_at": None,
                "note": "",
            }
        ]
        without_evidence = copy.deepcopy(base)
        without_evidence["last_verified_at"] = "2026-07-13"

        index = build_reviewed_visit_info_index(
            [
                {"spot_id": "without_date", "visit_info": without_date},
                {"spot_id": "without_evidence", "visit_info": without_evidence},
            ]
        )

        self.assertEqual(index, {})

    def test_existing_visit_info_is_preserved_and_only_missing_catalog_fields_are_added(self):
        place = {
            "id": "jeju_indoor_literature_022",
            "visit_info": {
                "address": "사람이 확인한 주소",
                "phone": None,
                "operating_hours": "09:00~18:00",
                "official_url": "https://official.example.com",
                "reservation_url": None,
                "service_status": "active",
                "notice": None,
                "verification_status": "verified",
                "last_verified_at": "2026-06-01",
                "missing_fields": ["phone", "reservation_url"],
                "evidence": [],
            },
        }

        enriched = enrich_places_with_visit_info([place], [catalog_row()])[0]["visit_info"]

        self.assertEqual(enriched["address"], "사람이 확인한 주소")
        self.assertEqual(enriched["phone"], "064-710-3490")
        self.assertEqual(enriched["operating_hours"], "09:00~18:00")
        self.assertEqual(enriched["official_url"], "https://official.example.com")
        self.assertEqual(enriched["verification_status"], "needs_check")
        self.assertEqual(enriched["last_verified_at"], "2026-06-01")
        self.assertEqual(enriched["source_updated_at"], "2025-07-30")
        self.assertEqual(enriched["evidence"][0]["fields"], ["phone"])

    def test_visit_info_for_place_returns_sanitized_fixed_shape(self):
        info = visit_info_for_place(
            {
                "visit_info": {
                    "address": "  제주 주소  ",
                    "phone": " 064-123-4567 ",
                    "official_url": "javascript:alert(1)",
                    "reservation_url": "https://booking.example.com/path",
                    "service_status": "unsupported",
                    "verification_status": "unsupported",
                    "last_verified_at": "not-a-date",
                    "missing_fields": ["official_url", "not_a_field", "official_url"],
                    "evidence": [
                        {
                            "fields": ["address"],
                            "source_url": "javascript:alert(1)",
                        }
                    ],
                    "internal_note": "must be dropped",
                }
            }
        )

        self.assertEqual(info["address"], "제주 주소")
        self.assertEqual(info["phone"], "064-123-4567")
        self.assertIsNone(info["official_url"])
        self.assertEqual(info["reservation_url"], "https://booking.example.com/path")
        self.assertEqual(info["service_status"], "unknown")
        self.assertEqual(info["verification_status"], "needs_check")
        self.assertIsNone(info["last_verified_at"])
        self.assertEqual(info["missing_fields"], ["official_url"])
        self.assertEqual(info["evidence"], [])
        self.assertEqual(set(info), set(empty_visit_info()))


if __name__ == "__main__":
    unittest.main()
