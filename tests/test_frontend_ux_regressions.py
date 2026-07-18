import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class FrontendUxRegressionTests(unittest.TestCase):
    def test_public_copy_does_not_expose_internal_search_terms(self):
        public_source = "\n".join(
            (WEB / name).read_text(encoding="utf-8")
            for name in (
                "index.html",
                "tourism-courses.html",
                "help-chatbot.html",
                "app.js",
                "tourism-courses.js",
                "help-chatbot.js",
            )
        )

        for phrase in (
            "RAG 조건 입력",
            "BM25 + 구조화 조건",
            "검수 코퍼스",
            "LLM 답변 ·",
            "브라우저는 API 키",
            "서버 답변 · 공식 위치 검색",
        ):
            self.assertNotIn(phrase, public_source)

    def test_share_feedback_preserves_the_button_icon_and_label(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")
        index = (WEB / "index.html").read_text(encoding="utf-8")

        self.assertIn("data-share-label", index)
        self.assertIn('button.querySelector("[data-share-label], span")', app)
        share_feedback = app[
            app.index("function setShareButtonFeedback") : app.index("function navTargetFromHash")
        ]
        self.assertNotIn("button.textContent =", share_feedback)

    def test_standard_modals_restore_focus_and_isolate_the_page(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")

        self.assertIn("function setStandardModalIsolation(active)", app)
        self.assertIn('node.setAttribute("inert", "")', app)
        self.assertIn("function trapStandardModalFocus(event)", app)
        self.assertIn("standardModalReturnFocus.set(modal, trigger)", app)
        self.assertIn("returnFocus.focus", app)

    def test_promo_close_restores_the_previous_section(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")

        self.assertIn("promoReturnHash = window.location.hash", app)
        self.assertIn('window.history.replaceState(null, "", promoReturnHash)', app)
        self.assertNotIn('state.activeNav = "map"', app)

    def test_public_typography_uses_four_readable_weight_levels(self):
        for name in ("styles.css", "tourism-courses.css", "help-chatbot.css"):
            css = (WEB / name).read_text(encoding="utf-8")
            weights = {int(value) for value in re.findall(r"font-weight:\s*(\d+)", css)}
            self.assertTrue(weights.issubset({400, 500, 600, 700}), (name, weights))

        styles = (WEB / "styles.css").read_text(encoding="utf-8")
        help_styles = (WEB / "help-chatbot.css").read_text(encoding="utf-8")
        tourism_styles = (WEB / "tourism-courses.css").read_text(encoding="utf-8")
        self.assertIn("font-size: 16px", styles[styles.index(".rag-query-section textarea {") :])
        self.assertIn("font-size: 16px", help_styles[help_styles.index(".helpbot-input {") :])
        self.assertIn("font-size: 16px", tourism_styles[tourism_styles.index(".tourism-input-shell input,") :])


if __name__ == "__main__":
    unittest.main()
