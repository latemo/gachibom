import json
import unittest

from src.help_chatbot_service import (
    HELP_CHATBOT_MAX_CONTEXT_LIST_ITEMS,
    HELP_CHATBOT_MAX_RECOMMENDATION_CONTEXT_BYTES,
    HELP_CHATBOT_SAFETY_NOTE,
    build_help_chatbot_reply,
    enforce_help_safety,
    normalize_help_history,
    normalize_help_recommendation_context,
)


class FakeHelpClient:
    def __init__(self):
        self.context = None

    def generate_reply(self, context, *, model):
        self.context = context
        return {
            "answer": f"{context['question']}에 대한 LLM 답변입니다.",
            "followups": ["점수는 어떻게 보나요?", "개인정보는 저장되나요?"],
            "handoff_checklist": ["방문 전 공식 정보 확인", "현장 문의"],
        }


class HelpChatbotServiceTests(unittest.TestCase):
    def test_build_help_chatbot_reply_with_fake_llm_client(self):
        client = FakeHelpClient()
        reply = build_help_chatbot_reply("휠체어 접근은 어떻게 확인하나요?", model="gpt-5-mini", client=client)

        self.assertEqual(reply["status"], "success")
        self.assertEqual(reply["model"], "gpt-5-mini")
        self.assertIn("LLM 답변", reply["answer"])
        self.assertEqual(len(reply["followups"]), 2)
        self.assertEqual(reply["safety_note"], HELP_CHATBOT_SAFETY_NOTE)
        self.assertNotIn("recommendation_context", client.context)

    def test_build_help_chatbot_reply_passes_normalized_recommendation_context(self):
        client = FakeHelpClient()
        reply = build_help_chatbot_reply(
            "이 장소가 추천된 이유는 뭔가요?",
            recommendation_context={
                "mode": "runtime",
                "traveler_summary": {
                    "required_accessibility": ["휠체어 접근", "장애인 화장실"],
                    "unknown_profile_field": ["제외됨"],
                },
                "selected_place": {
                    "spot_id": "spot-1",
                    "name": "제주문학관",
                    "score": {
                        "total": 84,
                        "grade": "B",
                        "confidence": "high",
                        "calculation_trace": {
                            "base_total": 80,
                            "bonuses": [{"id": "matched_rule", "label": "필수 조건 충족", "delta": 5}],
                            "deductions": [{"id": "missing_date", "label": "확인일 없음", "delta": -1}],
                            "caps": [{"id": "score_bounds", "label": "점수 범위", "before": 104, "after": 100}],
                            "final_total": 84,
                            "ignored_trace_field": "제외됨",
                        },
                        "ignored": "제외됨",
                    },
                    "fit_reasons": ["휠체어 접근 확인"],
                    "verification_status": "verified",
                    "blocked": False,
                    "block_reasons": ["추천 제외 조건 없음"],
                    "internal_note": "제외됨",
                },
                "unknown_top_level": "제외됨",
            },
            client=client,
        )

        self.assertEqual(reply["status"], "success")
        context = client.context["recommendation_context"]
        self.assertEqual(context["mode"], "runtime")
        self.assertEqual(context["selected_place"]["score"]["total"], 84)
        trace = context["selected_place"]["score"]["calculation_trace"]
        self.assertEqual(trace["bonuses"][0]["delta"], 5)
        self.assertEqual(trace["caps"][0]["before"], 104)
        self.assertNotIn("ignored_trace_field", trace)
        self.assertFalse(context["selected_place"]["blocked"])
        self.assertEqual(context["selected_place"]["block_reasons"], ["추천 제외 조건 없음"])
        self.assertNotIn("unknown_top_level", context)
        self.assertNotIn("internal_note", context["selected_place"])

    def test_normalize_recommendation_context_limits_fields_lists_text_and_urls(self):
        normalized = normalize_help_recommendation_context(
            {
                "mode": "STATIC",
                "traveler_summary": {
                    "avoid": [f"피할 조건 {index}" for index in range(20)],
                },
                "recommendation": {
                    "course": {
                        "title": "긴 코스 " * 100,
                        "route": [
                            {"order": index + 1, "spot_id": f"spot-{index}", "name": f"장소 {index}", "extra": "제외됨"}
                            for index in range(8)
                        ],
                    },
                    "fit_reasons": [f"적합 {index}" for index in range(20)],
                    "source_summary": [
                        {"title": "공식", "url": "https://example.org/place", "status": "verified"},
                        {"title": "잘못된 URL", "url": "javascript:alert(1)", "status": "verified"},
                    ],
                    "unexpected": {"nested": "제외됨"},
                },
            }
        )

        self.assertEqual(normalized["mode"], "static")
        self.assertEqual(len(normalized["traveler_summary"]["avoid"]), HELP_CHATBOT_MAX_CONTEXT_LIST_ITEMS)
        self.assertEqual(len(normalized["recommendation"]["course"]["route"]), 4)
        self.assertLessEqual(len(normalized["recommendation"]["course"]["title"]), 160)
        self.assertEqual(normalized["recommendation"]["source_summary"][0]["url"], "https://example.org/place")
        self.assertNotIn("url", normalized["recommendation"]["source_summary"][1])
        self.assertNotIn("unexpected", normalized["recommendation"])
        encoded = json.dumps(normalized, ensure_ascii=False).encode("utf-8")
        self.assertLessEqual(len(encoded), HELP_CHATBOT_MAX_RECOMMENDATION_CONTEXT_BYTES)

    def test_normalize_recommendation_context_rejects_invalid_shape(self):
        self.assertEqual(normalize_help_recommendation_context(["not", "an", "object"]), {})

    def test_normalize_recommendation_context_rejects_oversized_input(self):
        normalized = normalize_help_recommendation_context(
            {"mode": "runtime", "ignored": "가" * HELP_CHATBOT_MAX_RECOMMENDATION_CONTEXT_BYTES}
        )

        self.assertEqual(normalized, {})

    def test_build_help_chatbot_reply_without_client_reports_missing_key(self):
        reply = build_help_chatbot_reply("처음 어떻게 쓰나요?", client=None)

        self.assertEqual(reply["status"], "disabled_no_key")
        self.assertIn("OPENAI_API_KEY", reply["answer"])

    def test_normalize_help_history_keeps_safe_recent_messages(self):
        history = normalize_help_history(
            [
                {"role": "system", "content": "ignored"},
                {"role": "user", "content": "안녕"},
                {"role": "assistant", "content": "무엇을 도와드릴까요?"},
            ]
        )

        self.assertEqual(history, [{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "무엇을 도와드릴까요?"}])

    def test_enforce_help_safety_rewrites_overconfident_claims(self):
        text = enforce_help_safety("누구나 갈 수 있습니다. 휠체어도 100% 가능하고 문제없이 이동 가능합니다.")

        self.assertNotIn("100% 가능", text)
        self.assertNotIn("누구나 갈 수 있습니다", text)
        self.assertIn("현장 확인", text)


if __name__ == "__main__":
    unittest.main()
