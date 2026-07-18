import copy
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from src.rag_retrieval import MAX_LIMIT, retrieve_place_candidates


ROOT = Path(__file__).resolve().parents[1]


def load_places():
    return json.loads((ROOT / "data" / "jeju_accessible_spots.json").read_text(encoding="utf-8"))


def fixture_place(
    place_id,
    *,
    name="동일 장소",
    region="제주시",
    category="indoor",
    verification_status="verified",
    checked_at=None,
    wheelchair_state="yes",
    status="active",
):
    return {
        "id": place_id,
        "name": name,
        "region": region,
        "category": category,
        "summary": "휠체어 이용자가 확인할 수 있는 실내 문화 시설",
        "recommended_for": ["wheelchair_user"],
        "avoid_for": [],
        "accessibility": {
            "wheelchair_access": {
                "state": wheelchair_state,
                "note": "휠체어 접근 정보",
                "source_ref": "official",
            },
            "accessible_toilet": {
                "state": "yes",
                "note": "장애인 화장실",
                "source_ref": "official",
            },
        },
        "effort": {"walking_level": "low", "weather_sensitivity": "low"},
        "sources": [
            {
                "title": "공식 장소 정보",
                "url": f"https://example.org/{place_id}",
                "type": "public_agency",
            }
        ],
        "verification": {
            "status": verification_status,
            "checked_at": checked_at or date.today().isoformat(),
            "missing_fields": [],
        },
        "status": status,
        "safety_notes": ["방문 전 운영 상태 확인"],
        "operator_notes": [],
    }


class RagRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.places = load_places()

    def test_relevant_korean_query_prioritizes_real_grounded_place(self):
        results = retrieve_place_candidates(
            self.places,
            query="휠체어로 이용할 수 있는 실내 문학관과 장애인 화장실",
            limit=5,
        )

        names = [item["place"]["name"] for item in results]
        self.assertEqual(names[0], "제주문학관")
        self.assertIn("제주문학관", names)
        self.assertGreater(results[0]["retrieval_score"], results[-1]["retrieval_score"])
        self.assertTrue(any("장소명" in reason for reason in results[0]["retrieval_reasons"]))

    def test_unmatched_query_does_not_fall_back_to_trust_only_ranking(self):
        results = retrieve_place_candidates(
            self.places,
            query="존재하지않는검색어abcxyz",
            limit=5,
        )

        self.assertEqual(results, [])

    def test_structured_region_category_and_accessibility_are_hard_filters(self):
        results = retrieve_place_candidates(
            self.places,
            query="휠체어 실내 관람",
            intent={
                "region": "서귀포시",
                "category": "실내",
                "required_accessibility": ["휠체어 접근", "장애인 화장실"],
            },
            limit=20,
        )

        self.assertTrue(results)
        for result in results:
            place = result["place"]
            self.assertIn("서귀포시", place["region"])
            self.assertEqual(place["category"], "indoor")
            self.assertIn(place["accessibility"]["wheelchair_access"]["state"], {"yes", "partial"})
            self.assertIn(place["accessibility"]["accessible_toilet"]["state"], {"yes", "partial"})
            self.assertIn("required_accessibility", result["trace"]["filters_applied"])

    def test_returns_place_copy_and_does_not_mutate_input(self):
        places = copy.deepcopy(self.places[:4])
        original = copy.deepcopy(places)

        results = retrieve_place_candidates(places, query="숲길 휴식", limit=2)

        self.assertEqual(places, original)
        self.assertIsNot(results[0]["place"], places[0])
        results[0]["place"]["name"] = "변경됨"
        self.assertEqual(places, original)

    def test_order_is_stable_when_input_order_changes(self):
        query = "휠체어 실내 장애인 화장실 휴식"
        forward = retrieve_place_candidates(self.places, query=query, limit=20)
        reverse = retrieve_place_candidates(list(reversed(self.places)), query=query, limit=20)

        self.assertEqual(
            [item["place"]["id"] for item in forward],
            [item["place"]["id"] for item in reverse],
        )
        self.assertEqual(
            [item["retrieval_score"] for item in forward],
            [item["retrieval_score"] for item in reverse],
        )

    def test_limit_is_validated(self):
        for invalid in (0, -1, MAX_LIMIT + 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    retrieve_place_candidates(self.places, limit=invalid)
        for invalid in (True, 1.5, "3"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(TypeError):
                    retrieve_place_candidates(self.places, limit=invalid)

    def test_evidence_contains_source_and_verification_provenance(self):
        result = retrieve_place_candidates(self.places, query="제주문학관", limit=1)[0]
        evidence = result["evidence_bundle"]

        self.assertEqual(evidence["place_id"], result["place"]["id"])
        self.assertIn(evidence["verification"]["status"], {"verified", "partial", "needs_check"})
        self.assertRegex(evidence["verification"]["checked_at"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(evidence["sources"])
        for source in evidence["sources"]:
            self.assertRegex(source["evidence_id"], r"^ev_[0-9a-f]{16}$")
            self.assertTrue(source["title"])
            self.assertTrue(source["url"].startswith(("https://", "http://")))
            self.assertEqual(source["checked_at"], evidence["verification"]["checked_at"])
            self.assertEqual(source["status"], evidence["verification"]["status"])

    def test_as_of_controls_freshness_and_evidence_ids_are_stable(self):
        place = fixture_place("dated", checked_at="2026-01-01")

        recent = retrieve_place_candidates(
            [place], query="휠체어 실내", limit=1, as_of=date(2026, 6, 30)
        )[0]
        stale = retrieve_place_candidates(
            [place], query="휠체어 실내", limit=1, as_of=date(2027, 1, 2)
        )[0]

        self.assertEqual(recent["evidence_bundle"]["verification"]["freshness"], "recent")
        self.assertEqual(stale["evidence_bundle"]["verification"]["freshness"], "stale")
        self.assertEqual(
            recent["evidence_bundle"]["sources"][0]["evidence_id"],
            stale["evidence_bundle"]["sources"][0]["evidence_id"],
        )

    def test_verification_and_freshness_conservatively_break_equal_relevance(self):
        recent = fixture_place("recent")
        stale = fixture_place(
            "stale",
            verification_status="needs_check",
            checked_at=(date.today() - timedelta(days=500)).isoformat(),
        )

        results = retrieve_place_candidates([stale, recent], query="휠체어 실내 문화 시설", limit=2)

        self.assertEqual([item["place"]["id"] for item in results], ["recent", "stale"])
        self.assertEqual(results[0]["evidence_bundle"]["verification"]["freshness"], "recent")
        self.assertEqual(results[1]["evidence_bundle"]["verification"]["freshness"], "stale")
        self.assertGreater(results[0]["trace"]["components"]["verification"], results[1]["trace"]["components"]["verification"])

    def test_trace_does_not_retain_raw_query_or_intent_values(self):
        sensitive_query = "홍길동 01012345678 휠체어"
        sensitive_region = "비공개병원"
        result = retrieve_place_candidates(
            [fixture_place("privacy", region=sensitive_region)],
            query=sensitive_query,
            intent={"region": sensitive_region},
            limit=1,
        )[0]
        serialized_trace = json.dumps(result["trace"], ensure_ascii=False)

        self.assertNotIn("홍길동", serialized_trace)
        self.assertNotIn("01012345678", serialized_trace)
        self.assertNotIn(sensitive_region, serialized_trace)
        self.assertNotIn("query", result["trace"])

    def test_hidden_and_unavailable_cards_are_not_returned(self):
        active = fixture_place("active")
        hidden = fixture_place("hidden", status="hidden")
        unavailable = fixture_place("unavailable", verification_status="unavailable")

        results = retrieve_place_candidates([hidden, unavailable, active], query="실내", limit=3)

        self.assertEqual([item["place"]["id"] for item in results], ["active"])


if __name__ == "__main__":
    unittest.main()
