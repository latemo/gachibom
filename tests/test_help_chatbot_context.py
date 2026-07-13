import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELP_SCRIPT = ROOT / "web" / "help-chatbot.js"
APP_SCRIPT = ROOT / "web" / "app.js"


class HelpChatbotContextTests(unittest.TestCase):
    def test_help_request_includes_current_recommendation_context(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const path = process.argv[1];
let source = fs.readFileSync(path, "utf8");
source = source.replace(/\}\)\(\);\s*$/, `
globalThis.__helpContextTest = {
  currentRecommendationContext,
  buildHelpRequestBody
};
})();
`);
const recommendationContext = {
  mode: "runtime",
  traveler_summary: { traveler_type: ["wheelchair_user"] },
  selected_place: { spot_id: "place-1", name: "테스트 장소" }
};
const context = {
  console,
  window: {
    location: { search: "" },
    GachibomRecommendationContext: () => recommendationContext
  },
  document: { addEventListener() {} },
  URL,
  URLSearchParams,
  setTimeout,
  clearTimeout
};
vm.runInNewContext(source, context);
const body = context.__helpContextTest.buildHelpRequestBody("왜 추천됐나요?", []);
if (body.question !== "왜 추천됐나요?") throw new Error("question missing");
if (body.recommendation_context.mode !== "runtime") throw new Error("mode missing");
if (body.recommendation_context.selected_place.name !== "테스트 장소") throw new Error("place missing");
delete context.window.GachibomRecommendationContext;
const withoutProvider = context.__helpContextTest.buildHelpRequestBody("일반 질문", []);
if ("recommendation_context" in withoutProvider) throw new Error("missing provider must omit context");
context.window.GachibomRecommendationContext = () => { throw new Error("provider failed"); };
const failedProvider = context.__helpContextTest.buildHelpRequestBody("일반 질문", []);
if ("recommendation_context" in failedProvider) throw new Error("failed provider must omit context");
"""
        result = subprocess.run(
            ["node", "-e", harness, str(HELP_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_app_exposes_bounded_recommendation_context_provider(self):
        script = APP_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("window.GachibomRecommendationContext = helpRecommendationContext", script)
        self.assertIn("if (!state.data)", script)
        self.assertIn('mode: state.runtimeScenario ? "runtime" : "static"', script)
        self.assertIn("const place = state.detailCollapsed ? null : selectedPlace(scenario)", script)
        self.assertIn("selected_place: place ?", script)
        self.assertIn("source_summary: (place.source_summary || []).slice(0, 3)", script)
        self.assertIn('return "실시간 계산 추천 반영 완료"', script)
        self.assertIn('"사전 계산 추천 사용"', script)
        self.assertIn("function scoreCalculationTrace(place)", script)
        self.assertIn("${breakdown.map((item) =>", script)
        self.assertNotIn("breakdown.slice(1, 5)", script)
        self.assertIn('source_trust: "정보 신뢰도"', script)


if __name__ == "__main__":
    unittest.main()
