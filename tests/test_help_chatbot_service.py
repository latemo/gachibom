import unittest

from src.help_chatbot_service import (
    HELP_CHATBOT_SAFETY_NOTE,
    build_help_chatbot_reply,
    enforce_help_safety,
    normalize_help_history,
)


class FakeHelpClient:
    def generate_reply(self, context, *, model):
        return {
            "answer": f"{context['question']}에 대한 LLM 답변입니다.",
            "followups": ["점수는 어떻게 보나요?", "개인정보는 저장되나요?"],
            "handoff_checklist": ["방문 전 공식 정보 확인", "현장 문의"],
        }


class HelpChatbotServiceTests(unittest.TestCase):
    def test_build_help_chatbot_reply_with_fake_llm_client(self):
        reply = build_help_chatbot_reply("휠체어 접근은 어떻게 확인하나요?", model="gpt-5-mini", client=FakeHelpClient())

        self.assertEqual(reply["status"], "success")
        self.assertEqual(reply["model"], "gpt-5-mini")
        self.assertIn("LLM 답변", reply["answer"])
        self.assertEqual(len(reply["followups"]), 2)
        self.assertEqual(reply["safety_note"], HELP_CHATBOT_SAFETY_NOTE)

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
