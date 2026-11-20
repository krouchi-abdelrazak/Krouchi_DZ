"""اختبارات المحرّك كاملة بمزوّد وهمي: ذاكرة، حلقة أدوات، ووسيط، وتنفيذ فعلي."""

import base64
import os
import sys
import tempfile
import types
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz import control
from krouchi_dz.broker import READONLY_ALLOWED, request_summary
from krouchi_dz.documents import PDF_UNREADABLE, extract_text
from krouchi_dz.engine import (
    ATTACH_VISION_UNSUPPORTED_TEXT,
    ORIENTATION_AR,
    ORIENTATION_EN,
    VISION_UNSUPPORTED_TEXT,
    ChatEngine,
    prepare_attachment,
)
from krouchi_dz.providers import (
    TOOLS,
    TOOL_NAMES,
    ChatResult,
    MockProvider,
    ProviderError,
    ToolCall,
)
from krouchi_dz.remote import (
    FakeInputSink,
    FakeScreenSource,
    NullInputSink,
    UnsupportedScreenSource,
)


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
        # تحويل v3.4 (الواجهة المشتركة): الإرسال يُحسَم من الواجهة
        # المشتركة وحدها، فتضبط التركيبة واجهة صريحة يعمل بها كل
        # بوتات هذه الاختبارات مهما كان مزوّدها/نموذجها المخزَّنان.
        engine.set_shared_api("openrouter", "fixture-model")
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
        # التعليمات النظامية وصلت للمزوّد في أول الرسائل — بعد
        # التوجيه المدمج (v3.4) الذي يتصدّر محتوى النظام دائماً.
        sent = self.mock.calls[0]["messages"]
        self.assertEqual(sent[0]["role"], "system")
        self.assertTrue(sent[0]["content"].endswith("\n\nكن ودوداً"))

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


class TestTypingTools(EngineFixture):
    """أداتا الكتابة في أي برنامج (الإصدار 3.4.1): type_text تضخّ النص
    بحقن يونيكود في النافذة المركّزة، وpress_keys تضغط مفتاحاً أو
    تركيبة — وكلتاهما تقود مصرف إدخال remote نفسه الذي يقوده مسار
    إدخال الهاتف (/api/input عبر dispatch_input)، وتمرّان بالوسيط
    بنوعيهما الخاصّين «type_text» و«press_keys»."""

    def make_typing_engine(self, mock=None, ask_callback=None):
        engine = self.make_engine(mock, ask_callback=ask_callback)
        sink = FakeInputSink()
        engine.input_sink = sink
        return engine, sink

    def test_typing_tools_in_offered_schema(self):
        self.assertIn("type_text", TOOL_NAMES)
        self.assertIn("press_keys", TOOL_NAMES)
        type_entry = next(
            t for t in TOOLS if t["function"]["name"] == "type_text"
        )
        self.assertEqual(
            type_entry["function"]["parameters"]["required"], ["text"]
        )
        # وصف type_text يعلّم سير العمل: الفتح بـ open_target والحفظ
        self.assertIn("open_target", type_entry["function"]["description"])
        self.assertIn("press_keys", type_entry["function"]["description"])
        keys_entry = next(
            t for t in TOOLS if t["function"]["name"] == "press_keys"
        )
        self.assertEqual(
            keys_entry["function"]["parameters"]["required"], ["keys"]
        )
        self.assertIn("ctrl+s", keys_entry["function"]["description"])
        self.assertIn("tab", keys_entry["function"]["description"])

    def test_orientation_names_typing_workflow(self):
        for text in (ORIENTATION_AR, ORIENTATION_EN):
            self.assertIn("type_text", text)
            self.assertIn("press_keys", text)
            self.assertIn("ctrl+s", text)

    def test_type_text_calls_sink_with_exact_text(self):
        engine, sink = self.make_typing_engine()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        text = "محضر اجتماع مجلس التعليم — الحاضرون: الجميع"
        result = engine.perform_action(bot_id, "type_text", {"text": text})
        self.assertTrue(result["ok"])
        self.assertEqual(sink.calls, [("text", text)])
        self.assertIn(str(len(text)), result["output"])

    def test_type_text_long_text_fully_typed_in_chunks(self):
        engine, sink = self.make_typing_engine()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        text = "أ" * 4500
        result = engine.perform_action(bot_id, "type_text", {"text": text})
        self.assertTrue(result["ok"])
        typed = [call for call in sink.calls if call[0] == "text"]
        self.assertEqual(len(typed), 3)  # 2000 + 2000 + 500
        self.assertEqual("".join(call[1] for call in typed), text)

    def test_type_text_empty_or_missing_fails(self):
        engine, sink = self.make_typing_engine()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        for params in ({"text": ""}, {}, {"text": 42}):
            result = engine.perform_action(bot_id, "type_text", params)
            self.assertFalse(result["ok"], params)
        self.assertEqual(sink.calls, [])

    def test_press_keys_single_key_event(self):
        engine, sink = self.make_typing_engine()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        result = engine.perform_action(bot_id, "press_keys", {"keys": "enter"})
        self.assertTrue(result["ok"])
        self.assertEqual(sink.calls, [("key", "enter")])

    def test_press_keys_combo_events(self):
        engine, sink = self.make_typing_engine()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        for spec, expected in (
            ("ctrl+s", ("ctrl", "s")),
            ("alt+f4", ("alt", "f4")),
            ("shift+tab", ("shift", "tab")),
            ("CTRL + A", ("ctrl", "a")),
        ):
            sink.calls.clear()
            result = engine.perform_action(
                bot_id, "press_keys", {"keys": spec}
            )
            self.assertTrue(result["ok"], spec)
            self.assertEqual(sink.calls, [("combo", expected)], spec)

    def test_press_keys_invalid_names_fail_with_arabic_error(self):
        engine, sink = self.make_typing_engine()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        for spec in ("ctrl+banana", "banana", "ctrl+", "", "ctrl+ctrl"):
            result = engine.perform_action(
                bot_id, "press_keys", {"keys": spec}
            )
            self.assertFalse(result["ok"], spec)
            self.assertIn("فشل تنفيذ", result["error"], spec)
        self.assertEqual(sink.calls, [])

    def test_broker_gating_ask_mode_denies_without_approval(self):
        seen = []

        def deny(request):
            seen.append(request.action)
            return False

        engine, sink = self.make_typing_engine(ask_callback=deny)
        bot_id = engine.create_bot("كاتب", "openrouter")  # نمط ask
        for action, params in (
            ("type_text", {"text": "سرّي"}),
            ("press_keys", {"keys": "enter"}),
        ):
            result = engine.perform_action(bot_id, action, params)
            self.assertFalse(result["ok"], action)
            self.assertIn("رُفض الإجراء", result["error"], action)
        # الوسيط سُئل بالنوعين الخاصّين بكل أداة، ولم يُكتب شيء
        self.assertEqual(seen, ["type_text", "press_keys"])
        self.assertEqual(sink.calls, [])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(
            [row["action"] for row in audit], ["type_text", "press_keys"]
        )
        self.assertTrue(all(row["decision"] == "denied" for row in audit))

    def test_broker_gating_readonly_denies_and_full_allows(self):
        engine, sink = self.make_typing_engine()
        ro_id = engine.create_bot("قارئ", "openrouter", approval_mode="readonly")
        result = engine.perform_action(ro_id, "type_text", {"text": "x"})
        self.assertFalse(result["ok"])
        full_id = engine.create_bot("حرّ", "openrouter", approval_mode="full")
        result = engine.perform_action(
            full_id, "press_keys", {"keys": "ctrl+s"}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(sink.calls, [("combo", ("ctrl", "s"))])

    def test_unsupported_sink_is_clear_error_not_crash(self):
        engine = self.make_engine()
        engine.input_sink = NullInputSink()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        result = engine.perform_action(bot_id, "type_text", {"text": "سلام"})
        self.assertFalse(result["ok"])
        self.assertIn("غير مدعوم", result["error"])

    def test_tool_loop_types_via_approved_call(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="type_text",
                            arguments={"text": "بسم الله الرحمن الرحيم"},
                        )
                    ]
                ),
                ChatResult(text="كتبتُ الافتتاحية"),
            ]
        )
        engine, sink = self.make_typing_engine(
            provider, ask_callback=lambda req: True
        )
        bot_id = engine.create_bot("كاتب", "openrouter")
        reply = engine.send_message(bot_id, "اكتب الافتتاحية في Word")
        self.assertEqual(reply, "كتبتُ الافتتاحية")
        self.assertEqual(sink.calls, [("text", "بسم الله الرحمن الرحيم")])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["action"], "type_text")
        self.assertEqual(audit[0]["decision"], "allowed")


class TestReadingTools(EngineFixture):
    """أداتا القراءة (الإصدار 3.4.2): read_document تستخرج نصّ وثيقة
    (docx حقيقي بالمكتبة القياسية: فقرات وجداول بترتيب القراءة؛
    وملفات نصّية بفكّ ترميز تراجعي يقرأ ملفات ويندوز العربية
    cp1256)، وread_clipboard تقرأ الحافظة بقارئ control.get_clipboard
    نفسه خلف GET /api/clipboard. بوّابتهما بوّابة read_file حرفياً:
    نوعاهما في ACTIONS وفي READONLY_ALLOWED — فالقراءة مسموحة في
    نمط القراءة فقط، وتُسأل في نمط ask، وتُسمح في نمط full."""

    DOCX_XML = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        "<w:p><w:r><w:t>الجمهورية الجزائرية الديمقراطية الشعبية</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>موضوع الرسالة: </w:t></w:r>"
        "<w:r><w:t>تنظيم الاختبارات</w:t></w:r></w:p>"
        "<w:tbl>"
        "<w:tr>"
        "<w:tc><w:p><w:r><w:t>المادة</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>التوقيت</w:t></w:r></w:p></w:tc>"
        "</w:tr>"
        "<w:tr>"
        "<w:tc><w:p><w:r><w:t>الرياضيات</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>08:00</w:t></w:r></w:p></w:tc>"
        "</w:tr>"
        "</w:tbl>"
        "<w:p><w:r><w:t>تقبلوا فائق الاحترام</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )

    def write_docx(self, name="letter.docx"):
        path = Path(self.tmp.name) / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", self.DOCX_XML)
        return str(path)

    def test_reading_tools_in_offered_schema(self):
        self.assertIn("read_document", TOOL_NAMES)
        self.assertIn("read_clipboard", TOOL_NAMES)
        doc_entry = next(
            t for t in TOOLS if t["function"]["name"] == "read_document"
        )
        self.assertEqual(
            doc_entry["function"]["parameters"]["required"], ["path"]
        )
        self.assertIn("docx", doc_entry["function"]["description"])
        clip_entry = next(
            t for t in TOOLS if t["function"]["name"] == "read_clipboard"
        )
        self.assertEqual(
            clip_entry["function"]["parameters"]["required"], []
        )

    def test_orientation_names_reading_tools(self):
        for text in (ORIENTATION_AR, ORIENTATION_EN):
            self.assertIn("read_document", text)
            self.assertIn("read_clipboard", text)

    def test_read_document_docx_paragraphs_and_table_in_order(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        result = engine.perform_action(
            bot_id, "read_document", {"path": self.write_docx()}
        )
        self.assertTrue(result["ok"])
        out = result["output"]
        self.assertIn("الجمهورية الجزائرية الديمقراطية الشعبية", out)
        self.assertIn("موضوع الرسالة: تنظيم الاختبارات", out)
        self.assertIn("المادة | التوقيت", out)
        self.assertIn("الرياضيات | 08:00", out)
        # ترتيب القراءة: الفقرات والجدول كما في المستند
        self.assertLess(out.index("الجمهورية"), out.index("المادة | التوقيت"))
        self.assertLess(
            out.index("الرياضيات | 08:00"), out.index("تقبلوا فائق الاحترام")
        )

    def test_read_document_cp1256_arabic_text_file(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        text = "رسالة رسمية من مديرية التربية لولاية تلمسان"
        path = Path(self.tmp.name) / "letter.txt"
        path.write_bytes(text.encode("cp1256"))
        result = engine.perform_action(
            bot_id, "read_document", {"path": str(path)}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], text)

    def test_read_document_html_stripped_to_text(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        path = Path(self.tmp.name) / "page.html"
        path.write_text(
            "<html><body><h1>عنوان الرسالة</h1>"
            "<p>فقرة أولى</p><p>فقرة ثانية</p></body></html>",
            encoding="utf-8",
        )
        result = engine.perform_action(
            bot_id, "read_document", {"path": str(path)}
        )
        self.assertTrue(result["ok"])
        self.assertIn("عنوان الرسالة", result["output"])
        self.assertIn("فقرة أولى", result["output"])
        self.assertNotIn("<p>", result["output"])

    def test_read_document_truncation_cap_with_note(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        path = Path(self.tmp.name) / "long.txt"
        path.write_text("ب" * 13_000, encoding="utf-8")
        result = engine.perform_action(
            bot_id, "read_document", {"path": str(path)}
        )
        self.assertTrue(result["ok"])
        self.assertLess(len(result["output"]), 13_000)
        self.assertTrue(result["output"].startswith("ب" * 100))
        self.assertIn("12000", result["output"])
        self.assertIn("يستمرّ", result["output"])

    def test_read_document_corrupt_docx_clear_error(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        path = Path(self.tmp.name) / "bad.docx"
        path.write_bytes(b"this is not a zip archive at all")
        result = engine.perform_action(
            bot_id, "read_document", {"path": str(path)}
        )
        self.assertFalse(result["ok"])
        self.assertIn("تالف", result["error"])

    def test_read_document_unsupported_extension_clear_error(self):
        # ‏.doc (Word القديم الثنائي) ما زال غير مدعوم؛ أما .pdf فصار
        # مدعوماً بأفضل جهد منذ 3.6.0 (انظر TestUniversalReader).
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        path = Path(self.tmp.name) / "report.doc"
        path.write_bytes(b"\xd0\xcf\x11\xe0 fake")
        result = engine.perform_action(
            bot_id, "read_document", {"path": str(path)}
        )
        self.assertFalse(result["ok"])
        self.assertIn("غير مدعوم", result["error"])

    def test_read_document_missing_file_clear_error(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        ghost = str(Path(self.tmp.name) / "ghost.txt")
        result = engine.perform_action(
            bot_id, "read_document", {"path": ghost}
        )
        self.assertFalse(result["ok"])
        self.assertIn("غير موجود", result["error"])

    def test_read_clipboard_fake_getter_text_and_empty(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        with mock.patch.object(
            control, "get_clipboard", return_value="نصّ منسوخ من رسالة رسمية"
        ):
            result = engine.perform_action(bot_id, "read_clipboard", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], "نصّ منسوخ من رسالة رسمية")
        with mock.patch.object(control, "get_clipboard", return_value=""):
            result = engine.perform_action(bot_id, "read_clipboard", {})
        self.assertTrue(result["ok"])
        self.assertIn("الحافظة فارغة", result["output"])

    def test_reading_gating_parity_with_read_file(self):
        # عضوية READONLY_ALLOWED هي بوّابة القراءة نفسها
        self.assertIn("read_document", READONLY_ALLOWED)
        self.assertIn("read_clipboard", READONLY_ALLOWED)
        engine = self.make_engine()
        bot_id = engine.create_bot(
            "قارئ", "openrouter", approval_mode="readonly"
        )
        result = engine.perform_action(
            bot_id, "read_document", {"path": self.write_docx()}
        )
        self.assertTrue(result["ok"])
        with mock.patch.object(
            control, "get_clipboard", return_value="ملاحظة منسوخة"
        ):
            result = engine.perform_action(bot_id, "read_clipboard", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], "ملاحظة منسوخة")

    def test_reading_gating_ask_mode_denies_without_approval(self):
        seen = []

        def deny(request):
            seen.append(request.action)
            return False

        engine = self.make_engine(ask_callback=deny)
        bot_id = engine.create_bot("قارئ", "openrouter")  # نمط ask
        result = engine.perform_action(
            bot_id, "read_document", {"path": self.write_docx()}
        )
        self.assertFalse(result["ok"])
        self.assertIn("رُفض الإجراء", result["error"])
        self.assertEqual(seen, ["read_document"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["action"], "read_document")
        self.assertEqual(audit[0]["decision"], "denied")

    def test_tool_loop_reads_document(self):
        with tempfile.TemporaryDirectory() as own:
            path = Path(own) / "note.txt"
            path.write_text("نصّ الرسالة الرسمية كاملاً", encoding="utf-8")
            provider = MockProvider(
                [
                    ChatResult(
                        tool_calls=[
                            ToolCall(
                                id="c1", name="read_document",
                                arguments={"path": str(path)},
                            )
                        ]
                    ),
                    ChatResult(text="قرأتُ الرسالة ولخّصتها"),
                ]
            )
            engine = self.make_engine(
                provider, ask_callback=lambda req: True
            )
            bot_id = engine.create_bot("قارئ", "openrouter")
            reply = engine.send_message(bot_id, "اقرأ الرسالة ولخّصها")
        self.assertEqual(reply, "قرأتُ الرسالة ولخّصتها")
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("نصّ الرسالة الرسمية كاملاً", tool_msgs[0]["content"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["action"], "read_document")
        self.assertEqual(audit[0]["decision"], "allowed")


class VisionRejectingProvider:
    """مزوّد اختبار: يطلب see_screen أولاً، ثم يرفض أي نداء يحمل
    صورة بخطأ 400 كما يفعل نموذج نصّي حقيقي عبر نقطة OpenAI متوافقة،
    ويجيب نصّياً حين لا صورة في الرسائل."""

    supports_vision = True

    def __init__(self):
        self.calls = []

    def chat(self, messages, model, tools=None):
        self.calls.append(
            {"messages": list(messages), "model": model, "tools": tools}
        )
        if len(self.calls) == 1:
            return ChatResult(
                tool_calls=[
                    ToolCall(id="c1", name="see_screen", arguments={})
                ]
            )
        for message in messages:
            if isinstance(message.get("content"), list):
                raise ProviderError(
                    "HTTP 400 من المزوّد: {\"error\": {\"message\": "
                    "\"This model does not support image input "
                    "(multimodal content)\"}}"
                )
        return ChatResult(text="نموذجي نصّي — لا أرى الصور")


class TextOnlyMockProvider(MockProvider):
    """مزوّد وهمي معروف بأنه نصّي فقط (supports_vision=False)."""

    supports_vision = False


class TestSeeScreenTools(EngineFixture):
    """أداة العينين see_screen (الإصدار 3.5.0): تلتقط الشاشة بمصدر
    remote نفسه خلف /api/screen/frame (grab_jpeg بعرض 1024 وجودة
    70)، وتُسلّم الصورة للنموذج جزءَ image_url حقيقياً بعنوان
    data:image/jpeg;base64 في رسالة مستخدم تالية لنتيجة الأداة.
    بوّابتها بوّابة read_file (في ACTIONS وفي READONLY_ALLOWED).
    والتدهور آمن: رفض الصورة (400 يذكر الصورة/الرؤية) أو مزوّد
    معروف بأنه نصّي يجعل نتيجة الأداة نصّ VISION_UNSUPPORTED_TEXT
    الإرشادي — لا انهيار ولا ردّ فارغ."""

    def make_vision_engine(self, mock=None, ask_callback=None):
        engine = self.make_engine(mock, ask_callback=ask_callback)
        self.screen = FakeScreenSource(800, 600)
        engine.screen_source = self.screen
        return engine

    def expected_data_uri(self):
        # بايتات المصدر الوهمي الحتمية عند أول التقاط (العدّاد 0)
        probe = FakeScreenSource(800, 600)
        data = probe.grab_jpeg(max_width=1024, quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")

    def image_messages(self, call):
        return [
            m for m in call["messages"] if isinstance(m.get("content"), list)
        ]

    def test_see_screen_in_offered_schema(self):
        self.assertIn("see_screen", TOOL_NAMES)
        entry = next(
            t for t in TOOLS if t["function"]["name"] == "see_screen"
        )
        params = entry["function"]["parameters"]
        self.assertEqual(params["required"], [])
        self.assertIn("question", params["properties"])
        # الوصف يعلّم: انظر ثم افهم ثم تصرّف باليدين
        description = entry["function"]["description"]
        self.assertIn("type_text", description)
        self.assertIn("press_keys", description)
        self.assertIn("window_action", description)

    def test_orientation_names_eyes(self):
        for text in (ORIENTATION_AR, ORIENTATION_EN):
            self.assertIn("see_screen", text)

    def test_tool_loop_delivers_exact_image_part(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="see_screen",
                            arguments={"question": "ما البرنامج المفتوح؟"},
                        )
                    ]
                ),
                ChatResult(text="أرى المفكّرة مفتوحة"),
            ]
        )
        engine = self.make_vision_engine(
            provider, ask_callback=lambda req: True
        )
        bot_id = engine.create_bot("بصير", "openrouter")
        reply = engine.send_message(bot_id, "انظر إلى الشاشة")
        self.assertEqual(reply, "أرى المفكّرة مفتوحة")
        # النداء الثاني للمزوّد حمل الصورة جزءاً حقيقياً بعنوان
        # data URI مطابق لبايتات الالتقاط الوهمي حرفياً، وسؤال
        # البوت نصَّ الجزء المرافق.
        images = self.image_messages(provider.calls[1])
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["role"], "user")
        parts = images[0]["content"]
        self.assertEqual(
            parts[0], {"type": "text", "text": "ما البرنامج المفتوح؟"}
        )
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertEqual(parts[1]["image_url"]["url"], self.expected_data_uri())
        # نتيجة الأداة المحفوظة نصّية (لا صورة تنتفخ بها الذاكرة)،
        # والقرار مُدقّق بنوع see_screen.
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("التُقطت صورة الشاشة", tool_msgs[0]["content"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["action"], "see_screen")
        self.assertEqual(audit[0]["decision"], "allowed")

    def test_tool_loop_default_text_part_without_question(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(id="c1", name="see_screen", arguments={})
                    ]
                ),
                ChatResult(text="رأيتُ الشاشة"),
            ]
        )
        engine = self.make_vision_engine(
            provider, ask_callback=lambda req: True
        )
        bot_id = engine.create_bot("بصير", "openrouter")
        engine.send_message(bot_id, "انظر")
        images = self.image_messages(provider.calls[1])
        self.assertEqual(len(images), 1)
        self.assertIn(
            "صورة شاشة حاسوب المستخدم", images[0]["content"][0]["text"]
        )

    def test_vision_rejection_degrades_to_guidance_text(self):
        provider = VisionRejectingProvider()
        engine = self.make_vision_engine(provider)
        bot_id = engine.create_bot(
            "بصير", "openrouter", approval_mode="full"
        )
        reply = engine.send_message(bot_id, "انظر إلى الشاشة وأخبرني")
        self.assertEqual(reply, "نموذجي نصّي — لا أرى الصور")
        # ثلاثة نداءات: طلب الأداة، رفض الصورة، إعادة نصّية ناجحة.
        self.assertEqual(len(provider.calls), 3)
        retried = provider.calls[2]
        self.assertEqual(self.image_messages(retried), [])
        tool_msgs = [
            m for m in retried["messages"] if m["role"] == "tool"
        ]
        self.assertEqual(
            tool_msgs[0]["content"], VISION_UNSUPPORTED_TEXT
        )
        self.assertIn("Krouchi AI", VISION_UNSUPPORTED_TEXT)

    def test_known_text_only_provider_gets_guidance_without_image(self):
        provider = TextOnlyMockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(id="c1", name="see_screen", arguments={})
                    ]
                ),
                ChatResult(text="حسناً، سأعتمد على القراءة"),
            ]
        )
        engine = self.make_vision_engine(provider)
        bot_id = engine.create_bot(
            "بصير", "openrouter", approval_mode="full"
        )
        reply = engine.send_message(bot_id, "انظر")
        self.assertEqual(reply, "حسناً، سأعتمد على القراءة")
        # لا رسالة صورة أُدخلت أصلاً، ونتيجة الأداة هي الإرشاد نفسه.
        self.assertEqual(self.image_messages(provider.calls[1]), [])
        tool_msgs = [
            m for m in provider.calls[1]["messages"] if m["role"] == "tool"
        ]
        self.assertEqual(
            tool_msgs[0]["content"], VISION_UNSUPPORTED_TEXT
        )

    def test_non_vision_provider_error_still_raises(self):
        class ServerErrorProvider:
            def __init__(self):
                self.calls = 0

            def chat(self, messages, model, tools=None):
                self.calls += 1
                if self.calls == 1:
                    return ChatResult(
                        tool_calls=[
                            ToolCall(
                                id="c1", name="see_screen", arguments={}
                            )
                        ]
                    )
                raise ProviderError("HTTP 500 من المزوّد: عطل داخلي")

        engine = self.make_vision_engine(ServerErrorProvider())
        bot_id = engine.create_bot(
            "بصير", "openrouter", approval_mode="full"
        )
        with self.assertRaises(ProviderError):
            engine.send_message(bot_id, "انظر")

    def test_capture_failure_is_clear_error_not_crash(self):
        engine = self.make_engine()
        engine.screen_source = UnsupportedScreenSource()
        bot_id = engine.create_bot(
            "بصير", "openrouter", approval_mode="full"
        )
        result = engine.perform_action(bot_id, "see_screen", {})
        self.assertFalse(result["ok"])
        self.assertIn("غير مدعومة", result["error"])
        self.assertNotIn("image", result)

    def test_see_screen_gating_parity_with_read_file(self):
        self.assertIn("see_screen", READONLY_ALLOWED)
        engine = self.make_vision_engine()
        bot_id = engine.create_bot(
            "بصير", "openrouter", approval_mode="readonly"
        )
        result = engine.perform_action(bot_id, "see_screen", {})
        self.assertTrue(result["ok"])
        self.assertIn("التُقطت صورة الشاشة", result["output"])
        self.assertEqual(
            result["image"]["data_uri"], self.expected_data_uri()
        )
        self.assertEqual(result["image"]["question"], "")

    def test_see_screen_ask_mode_denies_without_approval(self):
        seen = []

        def deny(request):
            seen.append(request.action)
            return False

        engine = self.make_vision_engine(ask_callback=deny)
        bot_id = engine.create_bot("بصير", "openrouter")  # نمط ask
        result = engine.perform_action(
            bot_id, "see_screen", {"question": "ما هذا؟"}
        )
        self.assertFalse(result["ok"])
        self.assertIn("رُفض الإجراء", result["error"])
        self.assertEqual(seen, ["see_screen"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["action"], "see_screen")
        self.assertEqual(audit[0]["decision"], "denied")


# ======================================================================
# القارئ العام documents.extract_text (الإصدار 3.6.0): xlsx وPDF
# ======================================================================
_XLSX_WORKBOOK = (
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    "<sheets>"
    '<sheet name="الأولى" sheetId="1" r:id="rId1"/>'
    '<sheet name="الثانية" sheetId="2" r:id="rId2"/>'
    "</sheets></workbook>"
)
_XLSX_RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="urn:worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="urn:worksheet" Target="worksheets/sheet2.xml"/>'
    "</Relationships>"
)
_XLSX_SHARED = (
    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    "<si><t>الاسم</t></si><si><t>أحمد</t></si><si><t>ملاحظة أخيرة</t></si>"
    "</sst>"
)
_XLSX_SHEET1 = (
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    "<sheetData>"
    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c>'
    '<c r="C1" t="inlineStr"><is><t>داخلي</t></is></c></row>'
    '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>3.5</v></c></row>'
    "</sheetData></worksheet>"
)
_XLSX_SHEET2 = (
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    "<sheetData>"
    '<row r="1"><c r="A1" t="s"><v>2</v></c></row>'
    "</sheetData></worksheet>"
)


def build_xlsx_bytes() -> bytes:
    """مصنّف Excel صالح البنية يُبنى بـ zipfile كما تُبنى تركيبة docx."""
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", _XLSX_WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", _XLSX_RELS)
        archive.writestr("xl/sharedStrings.xml", _XLSX_SHARED)
        archive.writestr("xl/worksheets/sheet1.xml", _XLSX_SHEET1)
        archive.writestr("xl/worksheets/sheet2.xml", _XLSX_SHEET2)
    return buffer.getvalue()


def build_pdf_bytes(content_stream: bytes | None) -> bytes:
    """PDF حدّي: كائن محتوى واحد بتدفّق FlateDecode (أو بلا تدفّق)."""
    if content_stream is None:
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF"
    compressed = zlib.compress(content_stream)
    return (
        b"%PDF-1.4\n1 0 obj<</Length "
        + str(len(compressed)).encode("ascii")
        + b">>stream\n"
        + compressed
        + b"\nendstream\nendobj\n%%EOF"
    )


class TestUniversalReader(EngineFixture):
    """xlsx: نصوص مشتركة محلولة، أرقام كما هي، نصّ داخلي، صفوف
    بترتيب القراءة وأوراق بترتيب المصنّف، خلايا بـ « | ».
    PDF: نصّ Tj/TJ من تدفّقات FlateDecode؛ وبلا نصّ ⇒ رسالة
    PDF_UNREADABLE الواضحة (OCR غير متوفّر) — لا خرج مشوّش."""

    def test_xlsx_extract_text_direct(self):
        text = extract_text(build_xlsx_bytes(), "جدول.xlsx")
        self.assertEqual(
            text, "الاسم | 42 | داخلي\nأحمد | 3.5\nملاحظة أخيرة"
        )

    def test_xlsx_via_read_document(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        path = Path(self.tmp.name) / "نقاط.xlsx"
        path.write_bytes(build_xlsx_bytes())
        result = engine.perform_action(
            bot_id, "read_document", {"path": str(path)}
        )
        self.assertTrue(result["ok"], result)
        self.assertIn("أحمد | 3.5", result["output"])

    def test_xlsx_corrupt_clear_error(self):
        with self.assertRaises(ValueError) as ctx:
            extract_text(b"not a zip at all", "تالف.xlsx")
        self.assertIn("تالف", str(ctx.exception))

    def test_pdf_tj_text_extracts(self):
        data = build_pdf_bytes(b"BT /F1 12 Tf (Hello PDF) Tj ET")
        self.assertEqual(extract_text(data, "رسالة.pdf"), "Hello PDF")

    def test_pdf_tj_array_and_escapes(self):
        data = build_pdf_bytes(b"BT [(Hel) 80 (lo)] TJ ET")
        self.assertEqual(extract_text(data, "a.pdf"), "Hello")
        data2 = build_pdf_bytes(b"BT (a \\(b\\) c) Tj ET")
        self.assertEqual(extract_text(data2, "b.pdf"), "a (b) c")

    def test_pdf_without_text_is_clear_unreadable(self):
        data = build_pdf_bytes(None)
        with self.assertRaises(ValueError) as ctx:
            extract_text(data, "ممسوح.pdf")
        self.assertEqual(str(ctx.exception), PDF_UNREADABLE)
        self.assertIn("OCR", str(ctx.exception))

    def test_pdf_unreadable_via_read_document(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("قارئ", "openrouter", approval_mode="full")
        path = Path(self.tmp.name) / "ممسوح.pdf"
        path.write_bytes(build_pdf_bytes(None))
        result = engine.perform_action(
            bot_id, "read_document", {"path": str(path)}
        )
        self.assertFalse(result["ok"])
        self.assertIn("OCR", result["error"])

    def test_pdf_not_a_pdf_clear_error(self):
        with self.assertRaises(ValueError) as ctx:
            extract_text(b"plain text really", "x.pdf")
        self.assertIn("تالف", str(ctx.exception))

    def test_read_document_schema_mentions_new_formats(self):
        entry = next(
            t for t in TOOLS if t["function"]["name"] == "read_document"
        )
        description = entry["function"]["description"]
        self.assertIn("docx", description)
        self.assertIn("xlsx", description)
        self.assertIn("pdf", description)


# ======================================================================
# التعلّم والمهارات وذاكرة البوتات (الإصدار 3.6.0)
# ======================================================================
class TestSkillsMemoryTools(EngineFixture):
    """use_skill قراءة بحوكمة read_file؛ وsave_skill/remember كتابة
    مشكِّلة للسلوك (ask يسأل، readonly يرفض). فهرس المهارات
    والذاكرة يُحقنان في موجّه النظام بعد التوجيه المدمج."""

    def test_learning_tools_in_schema(self):
        for name in ("use_skill", "save_skill", "remember"):
            self.assertIn(name, TOOL_NAMES)
        save = next(t for t in TOOLS if t["function"]["name"] == "save_skill")
        self.assertEqual(
            save["function"]["parameters"]["required"],
            ["name", "instructions"],
        )
        use = next(t for t in TOOLS if t["function"]["name"] == "use_skill")
        self.assertEqual(use["function"]["parameters"]["required"], ["name"])
        rem = next(t for t in TOOLS if t["function"]["name"] == "remember")
        self.assertEqual(rem["function"]["parameters"]["required"], ["fact"])
        self.assertIn("use_skill", READONLY_ALLOWED)

    def test_orientation_teaches_learning(self):
        for text in (ORIENTATION_AR, ORIENTATION_EN):
            self.assertIn("use_skill", text)
            self.assertIn("save_skill", text)
            self.assertIn("remember", text)

    def test_prompt_injects_skills_index_and_memory(self):
        provider = MockProvider([ChatResult(text="تم")])
        engine = self.make_engine(provider)
        bot_id = engine.create_bot("متعلّم", "openrouter")
        other_id = engine.create_bot("آخر", "openrouter")
        engine.db.save_skill(
            "محضر اجتماع", "صيغة كتابة المحاضر", "اكتب الترويسة أولاً",
            origin="taught",
        )
        engine.db.add_memory(None, "المؤسسة: ثانوية بلقاسم محمد")
        engine.db.add_memory(bot_id, "المدير يفضّل الجداول المختصرة")
        engine.db.add_memory(other_id, "حقيقة تخصّ البوت الآخر")
        engine.send_message(bot_id, "ابدأ")
        system = provider.calls[0]["messages"][0]["content"]
        self.assertIn("محضر اجتماع — صيغة كتابة المحاضر", system)
        self.assertIn("المؤسسة: ثانوية بلقاسم محمد", system)
        self.assertIn("المدير يفضّل الجداول المختصرة", system)
        self.assertNotIn("حقيقة تخصّ البوت الآخر", system)
        # الفهرس بعد التوجيه المدمج وقبل تعليمات البوت الخاصة
        self.assertLess(
            system.index("use_skill"), system.index("محضر اجتماع")
        )

    def test_learning_context_empty_when_nothing_saved(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("جديد", "openrouter")
        self.assertEqual(engine.learning_context(bot_id), "")

    def test_use_skill_tool_loop(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="use_skill",
                            arguments={"name": "محضر اجتماع"},
                        )
                    ]
                ),
                ChatResult(text="كتبت المحضر بالصيغة المحفوظة"),
            ]
        )
        engine = self.make_engine(provider)
        bot_id = engine.create_bot(
            "كاتب", "openrouter", approval_mode="full"
        )
        engine.db.save_skill(
            "محضر اجتماع", "صيغة المحاضر", "الترويسة ثم الحضور ثم القرارات",
            origin="taught",
        )
        reply = engine.send_message(bot_id, "اكتب محضراً")
        self.assertEqual(reply, "كتبت المحضر بالصيغة المحفوظة")
        tool_msgs = [m for m in engine.history(bot_id) if m["role"] == "tool"]
        self.assertIn("الترويسة ثم الحضور ثم القرارات", tool_msgs[0]["content"])
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["action"], "use_skill")
        self.assertEqual(audit[0]["decision"], "allowed")

    def test_use_skill_unknown_name_lists_available(self):
        engine = self.make_engine()
        bot_id = engine.create_bot("كاتب", "openrouter", approval_mode="full")
        engine.db.save_skill("مهارة وحيدة", "", "تعليمات", origin="bot")
        result = engine.perform_action(
            bot_id, "use_skill", {"name": "غير موجودة"}
        )
        self.assertFalse(result["ok"])
        self.assertIn("غير موجودة", result["error"])
        self.assertIn("مهارة وحيدة", result["error"])

    def test_use_skill_readonly_allowed(self):
        engine = self.make_engine()
        bot_id = engine.create_bot(
            "قارئ", "openrouter", approval_mode="readonly"
        )
        engine.db.save_skill("مهارة", "وصف", "نفّذ كذا", origin="taught")
        result = engine.perform_action(bot_id, "use_skill", {"name": "مهارة"})
        self.assertTrue(result["ok"], result)
        self.assertIn("نفّذ كذا", result["output"])

    def test_save_skill_tool_loop_persists_as_bot_origin(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="save_skill",
                            arguments={
                                "name": "ردّ رسمي",
                                "description": "صيغة الردود الرسمية",
                                "instructions": "ابدأ بالبسملة الإدارية…",
                            },
                        )
                    ]
                ),
                ChatResult(text="حفظت الصيغة"),
                ChatResult(text="حاضر"),
            ]
        )
        engine = self.make_engine(provider)
        bot_id = engine.create_bot(
            "كاتب", "openrouter", approval_mode="full"
        )
        reply = engine.send_message(bot_id, "تعلّم هذه الصيغة")
        self.assertEqual(reply, "حفظت الصيغة")
        skill = engine.db.get_skill("ردّ رسمي")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["origin"], "bot")
        self.assertEqual(skill["instructions"], "ابدأ بالبسملة الإدارية…")
        # والمهارة الجديدة تظهر في فهرس موجّه الرسالة التالية
        engine.send_message(bot_id, "رسالة جديدة")
        system = provider.calls[2]["messages"][0]["content"]
        self.assertIn("ردّ رسمي — صيغة الردود الرسمية", system)

    def test_save_skill_readonly_denied(self):
        engine = self.make_engine()
        bot_id = engine.create_bot(
            "قارئ", "openrouter", approval_mode="readonly"
        )
        result = engine.perform_action(
            bot_id, "save_skill",
            {"name": "مهارة", "instructions": "تعليمات"},
        )
        self.assertFalse(result["ok"])
        self.assertIsNone(engine.db.get_skill("مهارة"))
        audit = engine.db.get_audit(bot_id=bot_id)
        self.assertEqual(audit[0]["action"], "save_skill")
        self.assertEqual(audit[0]["decision"], "denied")

    def test_save_skill_ask_denied_with_summary(self):
        seen = []

        def deny(request):
            seen.append(request)
            return False

        engine = self.make_engine(ask_callback=deny)
        bot_id = engine.create_bot("كاتب", "openrouter")  # نمط ask
        result = engine.perform_action(
            bot_id, "save_skill",
            {
                "name": "مهارة مرفوضة",
                "description": "وصفها",
                "instructions": "خطواتها",
            },
        )
        self.assertFalse(result["ok"])
        self.assertIsNone(engine.db.get_skill("مهارة مرفوضة"))
        self.assertEqual(seen[0].action, "save_skill")
        summary = request_summary(seen[0])
        self.assertIn("مهارة مرفوضة", summary)
        self.assertIn("خطواتها", summary)

    def test_remember_tool_loop(self):
        provider = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1", name="remember",
                            arguments={"fact": "اجتماع الأساتذة كل ثلاثاء"},
                        )
                    ]
                ),
                ChatResult(text="سأتذكّر"),
            ]
        )
        engine = self.make_engine(provider)
        bot_id = engine.create_bot(
            "ذاكر", "openrouter", approval_mode="full"
        )
        engine.send_message(bot_id, "تذكّر هذا")
        notes = engine.db.list_memory(bot_id)
        self.assertEqual([n["fact"] for n in notes], ["اجتماع الأساتذة كل ثلاثاء"])
        # تظهر في سياق تعلّم الرسالة التالية لهذا البوت
        self.assertIn(
            "اجتماع الأساتذة كل ثلاثاء", engine.learning_context(bot_id)
        )

    def test_remember_readonly_denied(self):
        engine = self.make_engine()
        bot_id = engine.create_bot(
            "قارئ", "openrouter", approval_mode="readonly"
        )
        result = engine.perform_action(
            bot_id, "remember", {"fact": "حقيقة"}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(engine.db.list_memory(bot_id), [])

    def test_broker_summaries_for_learning_actions(self):
        save_req = types.SimpleNamespace(
            action="save_skill",
            params={
                "name": "مهارة", "description": "وصف",
                "instructions": "تعليمات",
            },
        )
        self.assertIn("مهارة", request_summary(save_req))
        rem_req = types.SimpleNamespace(
            action="remember", params={"fact": "حقيقة دائمة"}
        )
        self.assertIn("حقيقة دائمة", request_summary(rem_req))
        use_req = types.SimpleNamespace(
            action="use_skill", params={"name": "مهارة"}
        )
        self.assertIn("مهارة", request_summary(use_req))


# ======================================================================
# مرفقات المحادثة — زرّ + (الإصدار 3.6.0)
# ======================================================================
class AttachRejectingProvider:
    """مزوّد اختبار: يرفض أي نداء يحمل جزء صورة (400 بصري) كما يفعل
    نموذج نصّي عبر نقطة متوافقة، ويجيب نصّياً عند غياب الصور."""

    supports_vision = True

    def __init__(self):
        self.calls = []

    def chat(self, messages, model, tools=None):
        self.calls.append(
            {"messages": list(messages), "model": model, "tools": tools}
        )
        for message in messages:
            if isinstance(message.get("content"), list):
                raise ProviderError(
                    "HTTP 400: this model has no vision / image input"
                )
        return ChatResult(text="وصلت الرسالة نصّياً")


class TestChatAttachments(EngineFixture):
    """prepare_attachment (قارئ عام للوثائق + جزء صورة للصور) ومرور
    المرفقات عبر send_message: النصّية تلتحم بعنوان «📎 ملف مرفق»،
    والصور أجزاء حقيقية في الرسالة الحيّة فقط، والتدهور الآمن
    للنموذج النصّي كـ see_screen تماماً."""

    def test_prepare_attachment_text_and_docx(self):
        self.make_engine()
        txt = Path(self.tmp.name) / "ملاحظة.txt"
        txt.write_text("نصّ الملاحظة", encoding="utf-8")
        prepared = prepare_attachment(txt)
        self.assertEqual(prepared["kind"], "text")
        self.assertEqual(prepared["name"], "ملاحظة.txt")
        self.assertIn("نصّ الملاحظة", prepared["text"])
        docx = Path(self.tmp.name) / "رسالة.docx"
        with zipfile.ZipFile(docx, "w") as archive:
            archive.writestr(
                "word/document.xml", TestReadingTools.DOCX_XML
            )
        prepared_docx = prepare_attachment(docx)
        self.assertEqual(prepared_docx["kind"], "text")
        self.assertIn("تنظيم الاختبارات", prepared_docx["text"])

    def test_prepare_attachment_image(self):
        self.make_engine()
        png = Path(self.tmp.name) / "لقطة.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
        prepared = prepare_attachment(png)
        self.assertEqual(prepared["kind"], "image")
        self.assertTrue(
            prepared["data_uri"].startswith("data:image/png;base64,")
        )

    def test_prepare_attachment_errors(self):
        self.make_engine()
        with self.assertRaises(ValueError) as ctx:
            prepare_attachment(Path(self.tmp.name) / "غائب.txt")
        self.assertIn("غير موجود", str(ctx.exception))
        legacy = Path(self.tmp.name) / "قديم.doc"
        legacy.write_bytes(b"\xd0\xcf\x11\xe0")
        with self.assertRaises(ValueError) as ctx:
            prepare_attachment(legacy)
        self.assertIn("غير مدعوم", str(ctx.exception))

    def test_text_attachment_reaches_provider_and_history(self):
        provider = MockProvider([ChatResult(text="لخّصت الرسالة")])
        engine = self.make_engine(provider)
        bot_id = engine.create_bot("ملخّص", "openrouter")
        reply = engine.send_message(
            bot_id, "لخّص هذا",
            attachments=[
                {
                    "kind": "text", "name": "رسالة.txt",
                    "text": "نصّ الرسالة الرسمية كاملاً",
                }
            ],
        )
        self.assertEqual(reply, "لخّصت الرسالة")
        sent_user = provider.calls[0]["messages"][-1]
        self.assertEqual(sent_user["role"], "user")
        self.assertIn("📎 ملف مرفق: رسالة.txt", sent_user["content"])
        self.assertIn("نصّ الرسالة الرسمية كاملاً", sent_user["content"])
        stored = engine.history(bot_id)[0]
        self.assertIn("📎 ملف مرفق: رسالة.txt", stored["content"])

    def test_image_attachment_part_shape(self):
        provider = MockProvider([ChatResult(text="صورة واضحة")])
        engine = self.make_engine(provider)
        bot_id = engine.create_bot("بصير", "openrouter")
        engine.send_message(
            bot_id, "ما هذه؟",
            attachments=[
                {
                    "kind": "image", "name": "لقطة.png",
                    "data_uri": "data:image/png;base64,QUJD",
                }
            ],
        )
        sent_user = provider.calls[0]["messages"][-1]
        self.assertIsInstance(sent_user["content"], list)
        self.assertEqual(sent_user["content"][0]["type"], "text")
        self.assertIn("📎 صورة مرفقة: لقطة.png", sent_user["content"][0]["text"])
        self.assertEqual(
            sent_user["content"][1],
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,QUJD"},
            },
        )
        # المخزَّن نصّ فقط — لا base64 ينفخ قاعدة البيانات
        stored = engine.history(bot_id)[0]
        self.assertIn("📎 صورة مرفقة: لقطة.png", stored["content"])
        self.assertNotIn("QUJD", stored["content"])

    def test_image_attachment_text_only_provider_gets_guidance(self):
        provider = TextOnlyMockProvider([ChatResult(text="لا أرى")])
        engine = self.make_engine(provider)
        bot_id = engine.create_bot("نصّي", "openrouter")
        engine.send_message(
            bot_id, "صِف الصورة",
            attachments=[
                {
                    "kind": "image", "name": "صورة.png",
                    "data_uri": "data:image/png;base64,QUJD",
                }
            ],
        )
        sent_user = provider.calls[0]["messages"][-1]
        self.assertIsInstance(sent_user["content"], str)
        self.assertIn(ATTACH_VISION_UNSUPPORTED_TEXT, sent_user["content"])

    def test_image_attachment_vision_rejection_degrades(self):
        provider = AttachRejectingProvider()
        engine = self.make_engine(provider)
        bot_id = engine.create_bot("بصير", "openrouter")
        reply = engine.send_message(
            bot_id, "ما في الصورة؟",
            attachments=[
                {
                    "kind": "image", "name": "صورة.png",
                    "data_uri": "data:image/png;base64,QUJD",
                }
            ],
        )
        self.assertEqual(reply, "وصلت الرسالة نصّياً")
        self.assertEqual(len(provider.calls), 2)
        retried_user = provider.calls[1]["messages"][-1]
        self.assertIsInstance(retried_user["content"], str)
        self.assertIn(ATTACH_VISION_UNSUPPORTED_TEXT, retried_user["content"])


if __name__ == "__main__":
    unittest.main()
