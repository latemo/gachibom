import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from scripts import build_place_location_candidates as candidates


class _Headers:
    @staticmethod
    def get_content_charset():
        return "utf-8"


class _Response:
    headers = _Headers()

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def _place(spot_id, name, region="제주시"):
    return {"id": spot_id, "name": name, "region": region}


def _raw_candidate(*, lat="33.499", lon="126.531", name="후보 장소", place_id=10):
    return {
        "place_id": place_id,
        "licence": "must not be copied into each candidate",
        "osm_type": "node",
        "osm_id": 1234 + place_id,
        "lat": lat,
        "lon": lon,
        "category": "tourism",
        "type": "museum",
        "addresstype": "tourism",
        "name": name,
        "display_name": f"{name}, 제주특별자치도, 대한민국",
        "importance": 0.42,
        "address": {
            "road": "관덕로",
            "city": "제주시",
            "country": "대한민국",
            "country_code": "kr",
            "unsafe_provider_field": "drop me",
        },
        "namedetails": {
            "name": name,
            "name:ko": name,
            "name:en": "Candidate Place",
            "brand:wikidata": "drop me",
        },
        "extratags": {"phone": "drop me"},
    }


class PlaceLocationCandidateTests(unittest.TestCase):
    def test_requests_only_missing_places_filters_non_jeju_and_checkpoints_each_request(self):
        places = [
            _place("located", "기존 좌표 장소"),
            _place("missing_b", "두 번째 장소", "서귀포시"),
            _place("missing_a", "첫 번째 장소"),
        ]
        location_index = {"located": {"latitude": 33.4, "longitude": 126.5}}
        first_response = [
            _raw_candidate(name="제주 후보", place_id=1),
            _raw_candidate(
                lat="37.5665", lon="126.9780", name="서울 후보", place_id=2
            ),
        ]
        opener = Mock(side_effect=[_Response(first_response), _Response([])])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "location-candidates.json"
            real_atomic_write = candidates.atomic_write_json
            with (
                patch.object(candidates, "urlopen", opener),
                patch.object(candidates, "sleep") as sleep_mock,
                patch.object(
                    candidates,
                    "atomic_write_json",
                    wraps=real_atomic_write,
                ) as write_mock,
            ):
                result = candidates.build_candidate_queue(
                    places,
                    location_index,
                    output_path=output,
                    generated_at="2026-07-13",
                    max_requests=2,
                )

            self.assertEqual(write_mock.call_count, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)

        self.assertEqual(opener.call_count, 2)
        sleep_mock.assert_called_once_with(1.1)
        self.assertEqual([item["spot_id"] for item in result["items"]], ["missing_a", "missing_b"])
        self.assertEqual(result["items"][0]["status"], "candidates_found")
        self.assertEqual(result["items"][1]["status"], "no_candidates")
        self.assertEqual(len(result["items"][0]["candidates"]), 1)

        safe_candidate = result["items"][0]["candidates"][0]
        self.assertNotIn("licence", safe_candidate)
        self.assertNotIn("extratags", safe_candidate)
        self.assertNotIn("unsafe_provider_field", safe_candidate["address"])
        self.assertNotIn("brand:wikidata", safe_candidate["name_details"])
        self.assertEqual(safe_candidate["latitude"], 33.499)
        self.assertEqual(safe_candidate["longitude"], 126.531)

        for call in opener.call_args_list:
            request = call.args[0]
            query = parse_qs(urlsplit(request.full_url).query)
            self.assertEqual(query["format"], ["jsonv2"])
            self.assertEqual(query["countrycodes"], ["kr"])
            self.assertEqual(query["addressdetails"], ["1"])
            self.assertEqual(query["namedetails"], ["1"])
            self.assertLessEqual(int(query["limit"][0]), 3)
            self.assertIn("gachibom-jeju", request.get_header("User-agent"))

        self.assertEqual(
            set(result["items"][0]),
            {"spot_id", "name", "query", "status", "candidates"},
        )
        self.assertFalse(result["review_policy"]["automatic_override_promotion"])
        self.assertEqual(result["source"]["url"], candidates.NOMINATIM_SEARCH_URL)
        self.assertIn("license", result["source"])
        self.assertIn("usage_policy", result["source"])

    def test_reuses_completed_cache_and_does_not_spend_request_budget_on_it(self):
        places = [_place("cached", "캐시 장소"), _place("fresh", "새 장소")]
        cached_query = candidates.build_query(places[0])
        existing_output = {
            "items": [
                {
                    "spot_id": "cached",
                    "name": "캐시 장소",
                    "query": cached_query,
                    "status": "candidates_found",
                    "candidates": [_raw_candidate(name="캐시 후보", place_id=9)],
                }
            ]
        }
        opener = Mock(return_value=_Response([]))

        result = candidates.build_candidate_queue(
            places,
            {},
            existing_output=existing_output,
            generated_at="2026-07-13",
            max_requests=1,
            open_url=opener,
        )

        self.assertEqual(opener.call_count, 1)
        self.assertEqual(result["summary"]["cached_results"], 1)
        self.assertEqual(result["summary"]["requests_this_run"], 1)
        by_id = {item["spot_id"]: item for item in result["items"]}
        self.assertEqual(by_id["cached"]["status"], "candidates_found")
        self.assertEqual(by_id["fresh"]["status"], "no_candidates")

    def test_max_requests_leaves_a_deterministic_pending_batch(self):
        places = [
            _place("spot_c", "장소 C"),
            _place("spot_a", "장소 A"),
            _place("spot_b", "장소 B"),
        ]
        opener = Mock(return_value=_Response([]))

        result = candidates.build_candidate_queue(
            places,
            {},
            generated_at="2026-07-13",
            max_requests=1,
            open_url=opener,
        )

        self.assertEqual(opener.call_count, 1)
        self.assertEqual(
            [(item["spot_id"], item["status"]) for item in result["items"]],
            [
                ("spot_a", "no_candidates"),
                ("spot_b", "pending"),
                ("spot_c", "pending"),
            ],
        )
        self.assertEqual(result["summary"]["pending"], 2)

    def test_output_is_deterministic_for_reordered_places_and_cache(self):
        places = [_place("spot_b", "장소 B"), _place("spot_a", "장소 A")]
        cache_items = []
        for place in places:
            cache_items.append(
                {
                    "spot_id": place["id"],
                    "name": place["name"],
                    "query": candidates.build_query(place),
                    "status": "candidates_found",
                    "candidates": [_raw_candidate(name=place["name"], place_id=len(cache_items) + 1)],
                }
            )

        first = candidates.build_candidate_queue(
            places,
            {},
            existing_output={"items": cache_items},
            generated_at="2026-07-13",
            max_requests=0,
        )
        second = candidates.build_candidate_queue(
            list(reversed(places)),
            {},
            existing_output={"items": list(reversed(cache_items))},
            generated_at="2026-07-13",
            max_requests=0,
        )

        self.assertEqual(first, second)

    def test_stale_or_error_cache_is_not_reused_and_located_places_are_omitted(self):
        places = [_place("located", "좌표 있음"), _place("retry", "재시도 장소")]
        existing_output = {
            "items": [
                {
                    "spot_id": "retry",
                    "name": "재시도 장소",
                    "query": candidates.build_query(places[1]),
                    "status": "request_error",
                    "candidates": [],
                }
            ]
        }
        opener = Mock(return_value=_Response([]))

        result = candidates.build_candidate_queue(
            places,
            {"located": {"latitude": 33.4, "longitude": 126.5}},
            existing_output=existing_output,
            generated_at="2026-07-13",
            max_requests=1,
            open_url=opener,
        )

        self.assertEqual(opener.call_count, 1)
        self.assertEqual([item["spot_id"] for item in result["items"]], ["retry"])
        self.assertEqual(result["summary"]["already_located"], 1)
        self.assertEqual(result["summary"]["missing_locations"], 1)


if __name__ == "__main__":
    unittest.main()
