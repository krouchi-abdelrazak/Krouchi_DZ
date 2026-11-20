"""اختبارات المحرّك كاملة بمزوّد وهمي: ذاكرة، حلقة أدوات، ووسيط، وتنفيذ فعلي."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.engine import ChatEngine
from krouchi_dz.providers import TOOLS, TOOL_NAMES, ChatResult, MockProvider, ToolCall


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


class TestOpenTargetTool(EngineFixture):
    """أداة open_target في المحادثة (الإصدار 3.3.2): موجودة في المخطط
    المعروض على النموذج، وتمرّ بوسيط الموافقات بنوع «open_target»،
    وتُنفَّذ بفاتح control.open_target نفسه الذي يستعمله مسار تحكّم
    الهاتف — ورفض الوسيط يمنع الفتح قطعاً ولا يدّعي النموذج فتحاً."""

    def test_open_target_in_offered_schema(self):
        self.assertIn("open_target", TOOL_NAMES)
        entry = next(
            t for t in TOOLS if t["function"]["name"] == "open_target"
        )
        params = entry["function"]["parameters"]
        self.assertEqual(params["required"], ["target"])
        self.assertIn("target", params["properties"])
        # وصف run_command لا يناقضها: يحيل الفتح إليها صراحة
        run_cmd = next(
            t for t in TOOLS if t["function"]["name"] == "run_command"
        )
        self.assertIn("open_target", run_cmd["function"]["description"])

    def test_open_target_goes_through_broker_then_opener(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="open_target",
                            arguments={"target": "notepad"},
                        )
                    ]
                ),
                ChatResult(text="فتحتُ المفكّرة"),
            ]
        )
        engine = self.make_engine(provider)
        bot_id = engine.create_bot("فاتح", "openrouter", approval_mode="full")
        with mock.patch(
            "krouchi_dz.control.open_target"
        ) as opener, mock.patch.object(
            engine.broker, "authorize", wraps=engine.broker.authorize
        ) as authorize:
            reply = engine.send_message(bot_id, "افتح المفكّرة")
        self.assertEqual(reply, "فتحتُ المفكّرة")
        opener.assert_called_once_with("notepad")
        actions = [call.args[1] for call in authorize.call_args_list]
        self.assertIn("open_target", actions)
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("فُتح الهدف", tool_msgs[0]["content"])

    def test_open_target_denied_does_not_open(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="open_target",
                            arguments={"target": "cmd"},
                        )
                    ]
                ),
                ChatResult(text="حسناً، لن أفتح"),
            ]
        )
        engine = self.make_engine(provider, ask_callback=lambda req: False)
        bot_id = engine.create_bot("فاتح", "openrouter")
        with mock.patch("krouchi_dz.control.open_target") as opener:
            reply = engine.send_message(bot_id, "افتح موجّه الأوامر")
        self.assertEqual(reply, "حسناً، لن أفتح")
        opener.assert_not_called()
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("رُفض الإجراء", tool_msgs[0]["content"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["decision"], "denied")
        self.assertEqual(audit[0]["action"], "open_target")

    def test_perform_action_open_target_full_mode(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        with mock.patch("krouchi_dz.control.open_target") as opener:
            result = engine.perform_action(
                bot_id, "open_target", {"target": "https://example.com"}
            )
        self.assertTrue(result["ok"])
        self.assertIn("https://example.com", result["output"])
        opener.assert_called_once_with("https://example.com")

    def test_open_target_empty_target_fails(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        with mock.patch("krouchi_dz.control.open_target") as opener:
            result = engine.perform_action(
                bot_id, "open_target", {"target": "  "}
            )
        self.assertFalse(result["ok"])
        opener.assert_not_called()


class TestWindowTools(EngineFixture):
    """أداتا النوافذ في المحادثة (الإصدار 3.3.2): list_windows قراءة
    محضة بلا وسيط إطلاقاً تعيد بيانات طبقة التحكّم نفسها، و
    window_action تمرّ بالوسيط بنوع تحكّم الهاتف «window_control»
    وتُنفَّذ بمنفّذ control.default_window_executor نفسه — ورفض
    الوسيط يمنع التنفيذ قطعاً (لا مزيد من taskkill مرتجَل)."""

    def test_window_tools_in_offered_schema(self):
        self.assertIn("list_windows", TOOL_NAMES)
        self.assertIn("window_action", TOOL_NAMES)
        entry = next(
            t for t in TOOLS if t["function"]["name"] == "window_action"
        )
        params = entry["function"]["parameters"]
        self.assertEqual(params["required"], ["id", "action"])
        self.assertEqual(
            params["properties"]["action"]["enum"],
            ["focus", "minimize", "maximize", "close"],
        )

    def test_list_windows_no_broker_returns_control_data(self):
        engine = self.make_engine()
        # حتى نمط القراءة فقط: لا وسيط ولا موافقة لسرد النوافذ
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="readonly")
        fake = [
            {"id": 101, "title": "المفكّرة"},
            {"id": 202, "title": "موجّه الأوامر"},
        ]
        with mock.patch(
            "krouchi_dz.control.list_windows", return_value=fake
        ), mock.patch.object(
            engine.broker, "authorize", wraps=engine.broker.authorize
        ) as authorize:
            result = engine.perform_action(bot_id, "list_windows", {})
        self.assertTrue(result["ok"])
        self.assertIn("101", result["output"])
        self.assertIn("المفكّرة", result["output"])
        self.assertIn("202", result["output"])
        self.assertIn("موجّه الأوامر", result["output"])
        authorize.assert_not_called()

    def test_list_windows_empty(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        with mock.patch("krouchi_dz.control.list_windows", return_value=[]):
            result = engine.perform_action(bot_id, "list_windows", {})
        self.assertTrue(result["ok"])
        self.assertIn("لا نوافذ", result["output"])

    def test_window_action_goes_through_broker_then_executor(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="window_action",
                            arguments={"id": 202, "action": "close"},
                        )
                    ]
                ),
                ChatResult(text="أغلقتُ النافذة"),
            ]
        )
        engine = self.make_engine(provider)
        bot_id = engine.create_bot("مدير", "openrouter", approval_mode="full")
        with mock.patch(
            "krouchi_dz.control.default_window_executor"
        ) as executor, mock.patch.object(
            engine.broker, "authorize", wraps=engine.broker.authorize
        ) as authorize:
            reply = engine.send_message(bot_id, "أغلق موجّه الأوامر")
        self.assertEqual(reply, "أغلقتُ النافذة")
        executor.assert_called_once_with(202, "close")
        # الوسيط رأى نوع تحكّم الهاتف «window_control» لا اسم الأداة
        actions = [call.args[1] for call in authorize.call_args_list]
        self.assertIn("window_control", actions)
        self.assertNotIn("window_action", actions)
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("أُغلقت النافذة", tool_msgs[0]["content"])

    def test_window_action_denied_does_not_execute(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="window_action",
                            arguments={"id": 202, "action": "close"},
                        )
                    ]
                ),
                ChatResult(text="حسناً، لن أغلق"),
            ]
        )
        engine = self.make_engine(provider, ask_callback=lambda req: False)
        bot_id = engine.create_bot("مدير", "openrouter")
        with mock.patch(
            "krouchi_dz.control.default_window_executor"
        ) as executor:
            reply = engine.send_message(bot_id, "أغلق موجّه الأوامر")
        self.assertEqual(reply, "حسناً، لن أغلق")
        executor.assert_not_called()
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("رُفض الإجراء", tool_msgs[0]["content"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["decision"], "denied")
        self.assertEqual(audit[0]["action"], "window_control")

    def test_window_action_bad_action_fails(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        with mock.patch(
            "krouchi_dz.control.default_window_executor"
        ) as executor:
            result = engine.perform_action(
                bot_id, "window_action", {"id": 5, "action": "explode"}
            )
        self.assertFalse(result["ok"])
        executor.assert_not_called()


class TestClearConversationTool(EngineFixture):
    """أداة مسح المحادثة (الإصدار 3.3.2): تمسح سجلّ البوت الحالي وحده
    نهائياً، وتمرّ بالوسيط بنوع «clear_conversation» مع force_ask —
    يُسأل المستخدم دائماً ولو كان وضع البوت «full» (سابقة «power»)،
    والرفض لا يمسح شيئاً."""

    def test_clear_tool_in_offered_schema(self):
        self.assertIn("clear_conversation", TOOL_NAMES)
        entry = next(
            t for t in TOOLS if t["function"]["name"] == "clear_conversation"
        )
        params = entry["function"]["parameters"]
        self.assertEqual(params["required"], [])
        self.assertEqual(params["properties"], {})

    def test_full_mode_still_asks_and_denial_keeps_history(self):
        provider = MockProvider(
            [
                ChatResult(text="أهلاً"),
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="clear_conversation", arguments={}
                        )
                    ]
                ),
                ChatResult(text="حسناً، أبقيتُ السجلّ"),
            ]
        )
        asked = []

        def ask(req):
            asked.append(req)
            return False

        engine = self.make_engine(provider, ask_callback=ask)
        # حتى وضع الوصول الكامل لا يعفي من السؤال في هذا النوع
        bot_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        engine.send_message(bot_id, "سؤال يبقى")
        with mock.patch.object(
            engine.broker, "authorize", wraps=engine.broker.authorize
        ) as authorize:
            reply = engine.send_message(bot_id, "امسح المحادثة")
        self.assertEqual(reply, "حسناً، أبقيتُ السجلّ")
        # الوسيط استُشير بـ force_ask رغم نمط full، وبطاقة السؤال وصلت
        clear_calls = [
            c for c in authorize.call_args_list
            if c.args[1] == "clear_conversation"
        ]
        self.assertTrue(clear_calls)
        self.assertTrue(all(c.kwargs.get("force_ask") for c in clear_calls))
        self.assertEqual([r.action for r in asked], ["clear_conversation"])
        # الرفض: لا شيء مُسح — السجلّ السابق كامل
        contents = [m["content"] for m in engine.history(bot_id)]
        self.assertIn("سؤال يبقى", contents)
        self.assertIn("أهلاً", contents)
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("رُفض الإجراء", tool_msgs[0]["content"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["decision"], "denied")
        self.assertEqual(audit[0]["action"], "clear_conversation")

    def test_approval_deletes_only_that_bot(self):
        provider = MockProvider(
            [
                ChatResult(text="ردّ أ"),
                ChatResult(text="ردّ ب"),
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="clear_conversation", arguments={}
                        )
                    ]
                ),
                ChatResult(text="تم المسح"),
            ]
        )
        engine = self.make_engine(provider, ask_callback=lambda req: True)
        bot_a = engine.create_bot("أ", "openrouter")
        bot_b = engine.create_bot("ب", "openrouter")
        engine.send_message(bot_a, "سرّ أ")
        engine.send_message(bot_b, "سرّ ب")
        reply = engine.send_message(bot_a, "امسح كل شيء")
        self.assertEqual(reply, "تم المسح")
        # سجلّ ب لم يُمسّ إطلاقاً
        self.assertEqual(
            [m["content"] for m in engine.history(bot_b)], ["سرّ ب", "ردّ ب"]
        )
        # سجلّ أ: ما قبل المسح اختفى كله؛ تبقّى من جولة المسح نفسها
        # نتيجتُها وردُّها الختامي فقط (يُكتبان بعد نقطة الحذف)
        hist_a = engine.history(bot_a)
        contents_a = [m["content"] for m in hist_a]
        self.assertNotIn("سرّ أ", contents_a)
        self.assertNotIn("ردّ أ", contents_a)
        self.assertNotIn("امسح كل شيء", contents_a)
        self.assertEqual([m["role"] for m in hist_a], ["tool", "assistant"])
        self.assertIn("مُسح سجلّ", hist_a[0]["content"])
        self.assertEqual(hist_a[1]["content"], "تم المسح")
        audit = engine.db.get_audit(bot_id=bot_a)
        self.assertEqual(audit[0]["decision"], "allowed")
        self.assertEqual(audit[0]["action"], "clear_conversation")

    def test_perform_action_approval_empties_history(self):
        engine = self.make_engine(
            MockProvider([ChatResult(text="ردّ")]),
            ask_callback=lambda req: True,
        )
        bot_id = engine.create_bot("مساعد", "openrouter")
        engine.send_message(bot_id, "سؤال")
        self.assertEqual(len(engine.history(bot_id)), 2)
        result = engine.perform_action(bot_id, "clear_conversation", {})
        self.assertTrue(result["ok"])
        self.assertIn("مُسح سجلّ", result["output"])
        self.assertIn("2 رسالة", result["output"])
        self.assertEqual(engine.history(bot_id), [])


if __name__ == "__main__":
    unittest.main()
