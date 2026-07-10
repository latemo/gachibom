import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "web" / "help-chatbot.js"
STYLES = ROOT / "web" / "help-chatbot.css"


class HelpChatbotPresenceTests(unittest.TestCase):
    def test_hourly_presence_configuration_replaces_continuous_nudge(self):
        script = SCRIPT.read_text(encoding="utf-8")
        styles = STYLES.read_text(encoding="utf-8")

        self.assertIn("const HELP_PRESENCE_FIRST_DELAY = 15000", script)
        self.assertIn("const HELP_PRESENCE_DURATION = 7000", script)
        self.assertIn('nextHour.setHours(now.getHours() + 1, 0, 0, 100)', script)
        self.assertIn("gachibom:helpbot-presence-muted-date", script)
        self.assertNotIn("interval = 5600", script)
        self.assertNotIn("is-idle-active", styles)
        self.assertIn("is-presence-active", styles)

    def test_time_based_presence_messages_and_storage_keys(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const path = process.argv[1];
let source = fs.readFileSync(path, "utf8");
source = source.replace(/\}\)\(\);\s*$/, `
globalThis.__presenceTest = {
  helpbotPresenceDateKey,
  helpbotPresenceHourKey,
  helpbotPresenceMessage
};
})();
`);
const context = {
  console,
  window: {},
  document: { addEventListener() {} },
  URL,
  URLSearchParams,
  setTimeout,
  clearTimeout
};
vm.runInNewContext(source, context);
const helpers = context.__presenceTest;
const morning = new Date(2026, 6, 10, 9, 0, 0);
const noon = new Date(2026, 6, 10, 13, 0, 0);
const afternoon = new Date(2026, 6, 10, 16, 0, 0);
if (helpers.helpbotPresenceDateKey(morning) !== "2026-07-10") throw new Error("date key mismatch");
if (helpers.helpbotPresenceHourKey(morning) !== "2026-07-10T09") throw new Error("hour key mismatch");
if (!helpers.helpbotPresenceMessage(morning).includes("제주 코스")) throw new Error("morning prompt mismatch");
if (!helpers.helpbotPresenceMessage(noon).includes("쉬어가기")) throw new Error("noon prompt mismatch");
if (!helpers.helpbotPresenceMessage(afternoon).includes("접근성 정보")) throw new Error("afternoon prompt mismatch");
"""
        result = subprocess.run(
            ["node", "-e", harness, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
