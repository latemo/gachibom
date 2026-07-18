import unittest

from src.accessibility_resources import (
    ACCESSIBLE_TOILET,
    POWER_WHEELCHAIR_FAST_CHARGER,
    detect_nearby_resource_types,
    search_nearby_accessibility_resources,
)


class AccessibilityResourcesTests(unittest.TestCase):
    def test_detection_requires_both_nearby_and_search_intent(self):
        self.assertEqual(
            detect_nearby_resource_types("내 주변 장애인 화장실과 전동휠체어 충전소를 찾아줘"),
            (ACCESSIBLE_TOILET, POWER_WHEELCHAIR_FAST_CHARGER),
        )
        self.assertEqual(detect_nearby_resource_types("장애인 화장실이 있나요?"), ())

    def test_public_resources_are_sorted_by_distance(self):
        result = search_nearby_accessibility_resources(
            latitude=33.5000,
            longitude=126.5000,
            resource_types=[ACCESSIBLE_TOILET],
            public_toilets=[
                {"id": "far", "name": "먼 화장실", "latitude": 33.6000, "longitude": 126.6000},
                {"id": "near", "name": "가까운 화장실", "latitude": 33.5010, "longitude": 126.5010},
            ],
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual([item["id"] for item in result["nearby_results"]], ["near", "far"])
        self.assertEqual(result["retrieval"]["evidence_policy"], "public_source_required")

    def test_coordinates_outside_jeju_fail_closed(self):
        result = search_nearby_accessibility_resources(
            latitude=37.5665,
            longitude=126.9780,
            resource_types=[POWER_WHEELCHAIR_FAST_CHARGER],
        )

        self.assertEqual(result["status"], "outside_service_area")
        self.assertEqual(result["nearby_results"], [])


if __name__ == "__main__":
    unittest.main()
