"""اختبارات عملاء المزوّدين بنقل وهمي (fake transport) — بلا شبكة."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.config import ProviderConfig
from krouchi_dz.providers import (
    GeminiProvider,
    MockProvider,
    OpenAICompatibleProvider,
)


class FakeTransport:
    """يلتقط الطلب ويعيد ردّاً مُعدّاً سلفاً."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, payload):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        return self.response


class TestOpenAICompatible(unittest.TestCase):
    def setUp(self):
        self.cfg = ProviderConfig(
            name="openrouter", kind="openai",
            base_url="https://openrouter.ai/api/v1",
            secret_ref="openrouter", default_model="m",
        )

    def test_request_shape_and_text_reply(self):
        transport = FakeTransport(
            {"choices": [{"message": {"content": "مرحباً بك"}}]}
        )
        provider = OpenAICompatibleProvider(self.cfg, "KEY-1", transport=transport)
        result = provider.chat([{"role": "user", "content": "سلام"}], "model-x")
        self.assertEqual(result.text, "مرحباً بك")
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(call["headers"]["Authorization"], "Bearer KEY-1")
        self.assertEqual(call["payload"]["model"], "model-x")
        self.assertEqual(call["payload"]["messages"][0]["content"], "سلام")

    def test_tool_calls_parsed(self):
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path": "a.txt"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        )
        provider = OpenAICompatibleProvider(self.cfg, "KEY-1", transport=transport)
        result = provider.chat([], "m", tools=[{"type": "function"}])
        self.assertEqual(len(result.tool_calls), 1)
        tc = result.tool_calls[0]
        self.assertEqual(tc.name, "read_file")
        self.assertEqual(tc.arguments, {"path": "a.txt"})
        self.assertEqual(transport.calls[0]["payload"]["tools"],
                         [{"type": "function"}])


class TestGemini(unittest.TestCase):
    def test_request_shape_and_reply(self):
        cfg = ProviderConfig(
            name="gemini", kind="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            secret_ref="gemini", default_model="gemini-2.0-flash",
        )
        transport = FakeTransport(
            {"candidates": [{"content": {"parts": [{"text": "أهلاً"}]}}]}
        )
        provider = GeminiProvider(cfg, "GKEY", transport=transport)
        result = provider.chat(
            [
                {"role": "system", "content": "كن موجزاً"},
                {"role": "user", "content": "سلام"},
                {"role": "assistant", "content": "وعليكم السلام"},
                {"role": "user", "content": "كيف الحال؟"},
            ],
            "gemini-2.0-flash",
        )
        self.assertEqual(result.text, "أهلاً")
        call = transport.calls[0]
        self.assertIn("gemini-2.0-flash:generateContent", call["url"])
        self.assertEqual(call["headers"]["x-goog-api-key"], "GKEY")
        self.assertEqual(
            call["payload"]["systemInstruction"]["parts"][0]["text"], "كن موجزاً"
        )
        contents = call["payload"]["contents"]
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[1]["role"], "model")

    def test_image_parts_translated_to_inline_data(self):
        # أجزاء الصورة (شكل OpenAI: image_url بعنوان data:) تُترجَم
        # إلى inline_data بشكل Gemini، والنصّ يبقى جزءَ نصّ — حتى
        # ترى نماذج Gemini لقطة see_screen كالنقاط المتوافقة تماماً.
        cfg = ProviderConfig(
            name="gemini", kind="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            secret_ref="gemini", default_model="gemini-2.0-flash",
        )
        transport = FakeTransport(
            {"candidates": [{"content": {"parts": [{"text": "أرى الشاشة"}]}}]}
        )
        provider = GeminiProvider(cfg, "GKEY", transport=transport)
        result = provider.chat(
            [
                {"role": "user", "content": "انظر"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "ما هذا؟"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64,QUJD"
                            },
                        },
                    ],
                },
            ],
            "gemini-2.0-flash",
        )
        self.assertEqual(result.text, "أرى الشاشة")
        contents = transport.calls[0]["payload"]["contents"]
        self.assertEqual(contents[0]["parts"], [{"text": "انظر"}])
        self.assertEqual(
            contents[1]["parts"],
            [
                {"text": "ما هذا؟"},
                {"inline_data": {"mime_type": "image/jpeg", "data": "QUJD"}},
            ],
        )
        self.assertTrue(provider.supports_vision)


class TestMock(unittest.TestCase):
    def test_scripted_replies_and_recording(self):
        from krouchi_dz.providers import ChatResult

        mock = MockProvider([ChatResult(text="أول"), ChatResult(text="ثانٍ")])
        self.assertEqual(mock.chat([], "m").text, "أول")
        self.assertEqual(mock.chat([], "m").text, "ثانٍ")
        self.assertEqual(mock.chat([], "m").text, "ردّ تجريبي")
        self.assertEqual(len(mock.calls), 3)


if __name__ == "__main__":
    unittest.main()
