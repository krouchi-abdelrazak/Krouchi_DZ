"""اختبارات المحرّك كاملة بمزوّد وهمي: ذاكرة، حلقة أدوات، ووسيط، وتنفيذ فعلي."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.engine import ChatEngine
from krouchi_dz.providers import ChatResult, MockProvider, ToolCall


class EngineFixture(unittest.TestCase):
    """يبني محرّكاً في مجلد مؤقت بمزوّد وهمي يُحقن عبر مصنع المزوّدين."""

    def make_engine(self, mock=None, ask_callback=None, ask_timeout=60.0):
        self.tmp = tempfile.TemporaryDirectory()
        self.mock = mock if mock is not None else MockProvider()
        engine = ChatEngine(
            Path(self.tmp.name) / "data",
            ask_callback=ask_callback,
            ask_timeout=ask_timeout,
            provider_factory=lambda cfg, key: self.mock,
        )
        self.addCleanup(engine.close)
        self.addCleanup(self.tmp.cleanup)
        return engine


class TestChatMemory(EngineFixture):
    def test_reply_and_memory_saved(self):
        engine = self.make_engine(MockProvider([ChatResult(text="أهلاً بك")]))
        bot_id = engine.create_bot(
            "مساعد", "openrouter", system_prompt="كن ودوداً"
        )
        reply = engine.send_message(bot_id, "سلام")
        self.assertEqual(reply, "أهلاً بك")
        history = engine.history(bot_id)
        self.assertEqual([m["role"] for m in history], ["user", "assistant"])
        self.assertEqual(history[0]["content"], "سلام")
        # التعليمات النظامية وصلت للمزوّد في أول الرسائل
        sent = self.mock.calls[0]["messages"]
        self.assertEqual(sent[0]["role"], "system")
        self.assertEqual(sent[0]["content"], "كن ودوداً")

    def test_memory_survives_new_engine_instance(self):
        engine = self.make_engine(MockProvider([ChatResult(text="ردّ أول")]))
        bot_id = engine.create_bot("مساعد", "groq")
        engine.send_message(bot_id, "سؤال أول")
        data_dir = engine.data_dir
        engine.close()

        mock2 = MockProvider([ChatResult(text="ردّ ثانٍ")])
        engine2 = ChatEngine(
            data_dir, provider_factory=lambda cfg, key: mock2
        )
        self.addCleanup(engine2.close)
        engine2.send_message(bot_id, "سؤال ثانٍ")
        sent = mock2.calls[0]["messages"]
        contents = [m["content"] for m in sent]
        self.assertIn("سؤال أول", contents)
        self.assertIn("ردّ أول", contents)

    def test_unknown_bot_rejected(self):
        engine = self.make_engine()
        with self.assertRaises(ValueError):
            engine.send_message(4242, "سلام")


class TestToolLoop(EngineFixture):
    def test_write_file_via_approved_tool_call(self):
        out_dir = tempfile.TemporaryDirectory()
        self.addCleanup(out_dir.cleanup)
        target = Path(out_dir.name) / "out" / "note.txt"
        mock = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="write_file",
                            arguments={"path": str(target), "content": "نصّ محفوظ"},
                        )
                    ]
                ),
                ChatResult(text="تمّ الحفظ"),
            ]
        )
        engine = self.make_engine(mock, ask_callback=lambda req: True)
        bot_id = engine.create_bot("كاتب", "openrouter")
        reply = engine.send_message(bot_id, "احفظ ملاحظة")
        self.assertEqual(reply, "تمّ الحفظ")
        self.assertEqual(target.read_text(encoding="utf-8"), "نصّ محفوظ")
        # القرار مُدقّق، ونتيجة الأداة محفوظة في الذاكرة
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["decision"], "allowed")
        roles = [m["role"] for m in engine.history(bot_id)]
        self.assertIn("tool", roles)

    def test_denied_tool_call_does_not_execute(self):
        out_dir = tempfile.TemporaryDirectory()
        self.addCleanup(out_dir.cleanup)
        target = Path(out_dir.name) / "should_not_exist.txt"
        mock = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="write_file",
                            arguments={"path": str(target), "content": "x"},
                        )
                    ]
                ),
                ChatResult(text="حسناً، لن أكتب"),
            ]
        )
        engine = self.make_engine(mock, ask_callback=lambda req: False)
        bot_id = engine.create_bot("كاتب", "openrouter")
        reply = engine.send_message(bot_id, "اكتب")
        self.assertEqual(reply, "حسناً، لن أكتب")
        self.assertFalse(target.exists())
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["decision"], "denied")

    def test_no_callback_fails_closed_end_to_end(self):
        mock = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="run_command",
                            arguments={"command": "echo hi"},
                        )
                    ]
                ),
                ChatResult(text="انتهى"),
            ]
        )
        engine = self.make_engine(mock, ask_callback=None)
        bot_id = engine.create_bot("منفّذ", "openrouter")
        reply = engine.send_message(bot_id, "نفّذ")
        self.assertEqual(reply, "انتهى")
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("رُفض الإجراء", tool_msgs[0]["content"])


class TestPerformAction(EngineFixture):
    def test_read_write_round_trip_full_mode(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        path = str(Path(self.tmp.name) / "a.txt")
        w = engine.perform_action(
            bot_id, "write_file", {"path": path, "content": "محتوى"}
        )
        self.assertTrue(w["ok"])
        r = engine.perform_action(bot_id, "read_file", {"path": path})
        self.assertTrue(r["ok"])
        self.assertEqual(r["output"], "محتوى")

    def test_run_command_full_mode(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        cmd = f'"{sys.executable}" -c "print(\'krouchi-ok\')"'
        result = engine.perform_action(bot_id, "run_command", {"command": cmd})
        self.assertTrue(result["ok"])
        self.assertIn("krouchi-ok", result["output"])
        self.assertIn("رمز الخروج 0", result["output"])

    def test_readonly_blocks_writes(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="readonly")
        result = engine.perform_action(
            bot_id, "write_file", {"path": "x.txt", "content": "y"}
        )
        self.assertFalse(result["ok"])
        self.assertIn("القراءة فقط", result["error"])


if __name__ == "__main__":
    unittest.main()
