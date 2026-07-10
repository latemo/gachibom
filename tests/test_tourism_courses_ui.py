import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TourismCoursesUiTests(unittest.TestCase):
    def test_traveler_filter_selects_highest_ranked_course(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const path = process.argv[1];
let source = fs.readFileSync(path, "utf8");
source = source.replace(/\r?\ninitTourismCourses\(\);\s*$/, "");
source += `
renderCourseSelector = () => {};
renderCourse = () => {};
updateCourseUrl = () => {};
tourismState.courses = [
  { id: "current", recommendation_by_type: { wheelchair_user: "추천" } },
  { id: "best", recommendation_by_type: { wheelchair_user: "적극추천" } }
];
tourismState.selectedCourseId = "current";
tourismState.travelerType = "wheelchair_user";
refreshFilteredCourses({ syncUrl: false, selectFirst: true });
if (tourismState.selectedCourseId !== "best") {
  throw new Error("traveler filter did not select the highest-ranked course");
}
`;
vm.runInNewContext(source, { console, URL, URLSearchParams });
"""
        result = subprocess.run(
            ["node", "-e", harness, str(ROOT / "web" / "tourism-courses.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
