import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNTIME_DATA_FILES = {
    "data/jeju_accessible_spots.json",
    "data/place_location_overrides.json",
    "data/roadview_image_metadata.json",
    "data/tourism_weak_recommendation_courses.json",
    "data/place_catalog.roadview_facility.json",
    "data/place_visit_info_overrides.json",
}

BLOCKED_ROUTES = {
    r"/\.env(.*)",
    r"/src(.*)",
    r"/scripts(.*)",
    r"/tests(.*)",
    r"/docs(.*)",
    r"/api/(.*)\.py",
    r"/README\.md",
    r"/design-qa\.md",
    r"/help-chatbot\.html",
    r"/miro_service_concept\.html",
}


class DeploymentConfigTests(unittest.TestCase):
    def test_private_routes_are_blocked_before_filesystem_routing(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        routes = config["routes"]
        filesystem_index = next(index for index, route in enumerate(routes) if route.get("handle") == "filesystem")
        blocked = {
            route["src"]: index
            for index, route in enumerate(routes)
            if route.get("status") == 404 and "src" in route
        }

        self.assertEqual(BLOCKED_ROUTES - blocked.keys(), set())
        self.assertTrue(all(blocked[route] < filesystem_index for route in BLOCKED_ROUTES))

    def test_function_bundle_includes_only_runtime_data(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        function_config = config["functions"]["api/**/*.py"]
        pattern = function_config["includeFiles"]
        self.assertTrue(pattern.startswith("{") and pattern.endswith("}"))
        self.assertEqual(set(pattern[1:-1].split(",")), RUNTIME_DATA_FILES)
        self.assertIn("data/raw/**", function_config["excludeFiles"])

    def test_vercelignore_excludes_private_and_unused_files(self):
        lines = {
            line.strip()
            for line in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertNotIn("!.env.example", lines)
        self.assertTrue({f"!{path}" for path in RUNTIME_DATA_FILES}.issubset(lines))
        self.assertTrue(
            {
                "data/**",
                "scripts/",
                "/31. EARLYFONT_JEJUDOLDAM/",
                "web/README.md",
                "web/design-qa.md",
                "web/help-chatbot.html",
                "web/miro_service_concept.html",
                "web/qa-*.png",
                "web/assets/theme-*-editorial.png",
                "web/assets/jeju-final-map-panel*.png",
                "web/assets/media/gachibom-jeju-site-intro.mp4",
                "web/assets/media/gachibom-jeju-promo.mp4",
                "web/assets/media/gachibom-jeju-promo-20260710.mp4",
            }.issubset(lines)
        )


if __name__ == "__main__":
    unittest.main()
