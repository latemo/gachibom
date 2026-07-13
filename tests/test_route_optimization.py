import copy
import unittest

from src.route_optimization import optimize_course_route


class RouteOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.route = [
            {"order": 10, "spot_id": "a", "name": "A", "purpose": "A 목적"},
            {"order": 20, "spot_id": "b", "name": "B", "purpose": "B 목적"},
            {"order": 30, "spot_id": "c", "name": "C", "purpose": "C 목적"},
            {"order": 40, "spot_id": "d", "name": "D", "purpose": "D 목적"},
        ]
        self.locations = {
            "a": {"latitude": 33.4, "longitude": 126.0},
            "b": {"latitude": 33.4, "longitude": 126.3},
            "c": {"latitude": 33.4, "longitude": 126.1},
            "d": {"latitude": 33.4, "longitude": 126.2},
        }

    def test_finds_exact_shortest_open_path_without_mutating_input(self):
        original_route = copy.deepcopy(self.route)
        original_locations = copy.deepcopy(self.locations)

        optimized = optimize_course_route(self.route, self.locations)

        self.assertEqual([item["spot_id"] for item in optimized], ["a", "c", "d", "b"])
        self.assertEqual([item["order"] for item in optimized], [1, 2, 3, 4])
        self.assertEqual({item["spot_id"] for item in optimized}, {"a", "b", "c", "d"})
        optimized_b = next(item for item in optimized if item["spot_id"] == "b")
        self.assertEqual(optimized_b["purpose"], "B 목적")
        self.assertEqual(self.route, original_route)
        self.assertEqual(self.locations, original_locations)

    def test_is_deterministic_when_reverse_paths_have_the_same_distance(self):
        first = optimize_course_route(self.route, self.locations)
        second = optimize_course_route(self.route, self.locations)

        self.assertEqual(first, second)
        self.assertEqual(first[0]["spot_id"], "a")

    def test_keeps_original_order_when_any_coordinate_is_missing_or_invalid(self):
        cases = {
            "missing": {
                key: value for key, value in self.locations.items() if key != "c"
            },
            "not_finite": {**self.locations, "c": {"latitude": "nan", "longitude": 126.1}},
            "out_of_range": {**self.locations, "c": {"latitude": 133.4, "longitude": 126.1}},
        }

        for label, locations in cases.items():
            with self.subTest(label=label):
                optimized = optimize_course_route(self.route, locations)
                self.assertEqual(
                    [item["spot_id"] for item in optimized],
                    ["a", "b", "c", "d"],
                )
                self.assertEqual([item["order"] for item in optimized], [1, 2, 3, 4])

    def test_short_routes_keep_their_order_and_are_renumbered(self):
        optimized = optimize_course_route(self.route[:2], self.locations)

        self.assertEqual([item["spot_id"] for item in optimized], ["a", "b"])
        self.assertEqual([item["order"] for item in optimized], [1, 2])

    def test_routes_over_the_four_stop_contract_are_not_factorially_searched(self):
        route = self.route + [{"order": 50, "spot_id": "e", "name": "E"}]
        locations = {**self.locations, "e": {"latitude": 33.4, "longitude": 126.15}}

        optimized = optimize_course_route(route, locations)

        self.assertEqual(
            [item["spot_id"] for item in optimized],
            ["a", "b", "c", "d", "e"],
        )
        self.assertEqual([item["order"] for item in optimized], [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
