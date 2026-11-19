"""اختبارات الواجهة الرسومية (الخطوة 2) — Tkinter تحت شاشة افتراضية.

تُشغَّل تحت xvfb:  xvfb-run -a python3 -m unittest tests.test_gui -v
بلا أي شبكة: المحرّك بمزوّد وهمي (MockProvider) ونقل اكتشاف وهمي.
إن غابت الشاشة تُتخطّى الاختبارات كلها صراحة (لا تُزيَّف نتائج).
"""

import gc
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tkinter as tk

from krouchi_dz import i18n
from krouchi_dz.broker import ApprovalRequest
from krouchi_dz.discovery import ERR_AUTH, DiscoveryError
from krouchi_dz.engine import ChatEngine
from krouchi_dz.gui import (
    AddApiDialog,
    ApprovalDialog,
    AuditWindow,
    BotDialog,
    EngineRunner,
    KrouchiApp,
    PhoneLinkDialog,
    TasksWindow,
    _ApprovalBridge,
    control_setting_enabled,
    ip_label,
)
from krouchi_dz.providers import ChatResult, MockProvider, ToolCall
from krouchi_dz.server import CompanionServer
from krouchi_dz.tasks import TaskStore


def _display_available() -> bool:
    try:
        probe = tk.Tk()
        probe.destroy()
        return True
    except tk.TclError:
        return False


DISPLAY_OK = _display_available()


@unittest.skipUnless(DISPLAY_OK, "لا شاشة متاحة — شغّل الاختبارات تحت xvfb-run")
class GuiFixture(unittest.TestCase):
    """جذر Tk مخفي + مجلد مؤقت + مساعد جسّ للأحداث حتى شرط."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._destroy_root)

    def _destroy_root(self):
        # دورات مرجعية (نافذة ↔ مشغّل ↔ ردّ نداء) لا يحرّرها إلا جامع
        # الدورات؛ إن حرّرها على خيط المحرّك انهارت متغيرات Tk. نجمعها
        # هنا — على الخيط الرئيسي — قبل تدمير الجذر وبعده.
        gc.collect()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        gc.collect()

    def pump_until(self, predicate, timeout=8.0, message="انتهت مهلة الجسّ"):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return True
            time.sleep(0.01)
        self.root.update()
        self.assertTrue(predicate(), message)

    def make_runner(self, mock=None, get_transport=None):
        """محرّك حقيقي (بمزوّد وهمي) داخل خيط EngineRunner كما في الإنتاج."""
        self.mock = mock if mock is not None else MockProvider()
        self.bridge = _ApprovalBridge()
        data_dir = Path(self.tmp.name) / "data"
        mock_ref = self.mock

        def factory():
            return ChatEngine(
                data_dir,
                ask_callback=self.bridge.ask,
                ask_timeout=120.0,
                provider_factory=lambda cfg, key: mock_ref,
                get_transport=get_transport,
            )

        runner = EngineRunner(factory)
        runner.wait_ready()
        runner.attach(self.root)
        self.addCleanup(runner.shutdown)
        return runner


# ======================================================================
# بطاقة الموافقة
# ======================================================================
class TestApprovalDialog(GuiFixture):
    def make_request(self, action="write_file", params=None):
        return ApprovalRequest(
            bot_id=1,
            bot_name="بوت تجريبي",
            action=action,
            params=params or {"path": "/tmp/x.txt", "content": "نصّ"},
            mode="ask",
        )

    def test_shows_bot_action_and_target(self):
        dialog = ApprovalDialog(self.root, self.make_request())
        self.addCleanup(dialog.top.destroy)
        self.assertEqual(dialog.action_text, "كتابة ملف")
        self.assertIn("/tmp/x.txt", dialog.target_text)
        label_texts = []

        def collect(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    label_texts.append(str(child.cget("text")))
                collect(child)

        collect(dialog.top)
        self.assertTrue(any("بوت تجريبي" in t for t in label_texts), label_texts)
        self.assertTrue(any("كتابة ملف" in t for t in label_texts), label_texts)

    def test_allow_button_returns_true(self):
        dialog = ApprovalDialog(self.root, self.make_request())
        self.root.after(80, dialog.allow_button.invoke)
        self.assertTrue(dialog.show())
        self.assertTrue(dialog.result)

    def test_deny_button_returns_false(self):
        dialog = ApprovalDialog(self.root, self.make_request())
        self.root.after(80, dialog.deny_button.invoke)
        self.assertFalse(dialog.show())
        self.assertFalse(dialog.result)

    def test_window_close_is_deny(self):
        dialog = ApprovalDialog(self.root, self.make_request())

        def close_via_protocol():
            command = dialog.top.tk.call(
                "wm", "protocol", dialog.top, "WM_DELETE_WINDOW"
            )
            if command:
                dialog.top.tk.call(command)
            else:  # احتياط: نفس دالة الإغلاق التي يسجّلها البروتوكول
                dialog._on_close()

        self.root.after(80, close_via_protocol)
        self.assertFalse(dialog.show())
        self.assertFalse(dialog.result)

    def test_timeout_is_deny(self):
        dialog = ApprovalDialog(self.root, self.make_request(), timeout=1)
        started = time.monotonic()
        self.assertFalse(dialog.show())
        self.assertGreaterEqual(time.monotonic() - started, 0.9)

    def test_run_command_target_shown_verbatim(self):
        request = self.make_request(
            action="run_command", params={"command": "echo krouchi"}
        )
        dialog = ApprovalDialog(self.root, request)
        self.addCleanup(dialog.top.destroy)
        self.assertEqual(dialog.action_text, "تشغيل أمر")
        self.assertEqual(dialog.target_text, "echo krouchi")


# ======================================================================
# شاشة إدخال API (اكتشاف وهمي — بلا شبكة)
# ======================================================================
def fake_get_ok(url, headers, timeout=30.0):
    return {"data": [{"id": "model-a"}, {"id": "model-b"}]}


def fake_get_auth(url, headers, timeout=30.0):
    raise DiscoveryError("auth", ERR_AUTH)


class TestAddApiDialog(GuiFixture):
    def test_fetch_success_lists_models_and_verified_provider(self):
        runner = self.make_runner(get_transport=fake_get_ok)
        dialog = AddApiDialog(self.root, runner)
        self.addCleanup(dialog.top.destroy)
        self.pump_until(lambda: dialog.providers_loaded)
        dialog.url_var.set("https://api.example.com")
        dialog.key_var.set("sk-test-123")
        dialog.start_fetch()
        self.pump_until(lambda: dialog.fetch_finished)
        models = [dialog.models_list.get(i) for i in range(dialog.models_list.size())]
        self.assertEqual(models, ["model-a", "model-b"])
        self.assertIn("تمّ بنجاح", dialog.status_label.cget("text"))

        def provider_lines():
            return [
                dialog.providers_list.get(i)
                for i in range(dialog.providers_list.size())
            ]

        self.pump_until(
            lambda: any(
                "example" in line and "مُتحقَّق" in line
                for line in provider_lines()
            )
        )

    def test_fetch_auth_failure_shows_engine_error_verbatim(self):
        runner = self.make_runner(get_transport=fake_get_auth)
        dialog = AddApiDialog(self.root, runner)
        self.addCleanup(dialog.top.destroy)
        self.pump_until(lambda: dialog.providers_loaded)
        dialog.url_var.set("https://api.example.com")
        dialog.key_var.set("sk-wrong")
        dialog.start_fetch()
        self.pump_until(lambda: dialog.fetch_finished)
        self.assertEqual(dialog.status_label.cget("text"), ERR_AUTH)
        self.assertEqual(dialog.models_list.size(), 0)
        self.assertIsNotNone(dialog.discovery_result)
        self.assertFalse(dialog.discovery_result.ok)

    def test_empty_fields_rejected_without_network(self):
        runner = self.make_runner(get_transport=fake_get_ok)
        dialog = AddApiDialog(self.root, runner)
        self.addCleanup(dialog.top.destroy)
        dialog.start_fetch()
        self.assertIn("أدخل عنوان الأساس", dialog.status_label.cget("text"))


# ======================================================================
# نافذة البوت: إنشاء وتعديل
# ======================================================================
class TestBotDialog(GuiFixture):
    def test_create_bot_flow(self):
        runner = self.make_runner()
        dialog = BotDialog(self.root, runner)
        self.pump_until(lambda: dialog.providers_loaded)
        dialog.name_var.set("بوت الاختبار")
        dialog.provider_var.set("openrouter")
        dialog._on_provider_changed()
        dialog.model_var.set("test-model-1")
        self.assertEqual(dialog.mode_var.get(), "اسأل")  # الافتراضي
        dialog.save()
        self.pump_until(lambda: dialog.saved)
        bots = runner.call(lambda e: e.db.list_bots())
        self.assertEqual(len(bots), 1)
        bot = bots[0]
        self.assertEqual(bot["name"], "بوت الاختبار")
        self.assertEqual(bot["provider_name"], "openrouter")
        self.assertEqual(bot["model"], "test-model-1")
        self.assertEqual(bot["approval_mode"], "ask")

    def test_edit_bot_changes_mode_keeps_name(self):
        runner = self.make_runner()
        bot_id = runner.call(
            lambda e: e.create_bot("أصلي", "openrouter", model="m0")
        )
        bot = runner.call(lambda e: e.db.get_bot(bot_id))
        dialog = BotDialog(self.root, runner, bot=bot)
        self.pump_until(lambda: dialog.providers_loaded)
        dialog.mode_var.set("قراءة فقط")
        dialog.save()
        self.pump_until(lambda: dialog.saved)
        updated = runner.call(lambda e: e.db.get_bot(bot_id))
        self.assertEqual(updated["approval_mode"], "readonly")
        self.assertEqual(updated["name"], "أصلي")
        self.assertEqual(updated["model"], "m0")


# ======================================================================
# النافذة الرئيسية: بناء، إرسال، موافقة من الطرف إلى الطرف
# ======================================================================
class TestMainWindow(GuiFixture):
    def test_window_constructs_and_lists_bots(self):
        runner = self.make_runner()
        runner.call(lambda e: e.create_bot("بوت أ", "openrouter"))
        runner.call(lambda e: e.create_bot("بوت ب", "groq"))
        app = KrouchiApp(self.root, runner, self.bridge)
        self.pump_until(lambda: app.bots_list.size() == 2)
        self.assertIn("بوت أ", app.bots_list.get(0))
        self.assertIn("بوت ب", app.bots_list.get(1))
        self.assertIsNotNone(app.selected_bot_id)

    def test_send_message_flow(self):
        mock = MockProvider([ChatResult(text="ردّ الواجهة")])
        runner = self.make_runner(mock=mock)
        bot_id = runner.call(lambda e: e.create_bot("محادث", "openrouter"))
        app = KrouchiApp(self.root, runner, self.bridge)
        self.pump_until(lambda: app.bots_list.size() == 1)
        app.select_bot(bot_id)
        app.entry_var.set("سلام")
        app.send_current()
        self.pump_until(
            lambda: not app._working
            and "ردّ الواجهة" in app.chat_text.get("1.0", "end")
        )
        self.assertEqual(app.entry_var.get(), "")
        history = runner.call(lambda e: e.history(bot_id))
        self.assertEqual([m["role"] for m in history], ["user", "assistant"])

    def test_approval_card_end_to_end_allows_write(self):
        out_dir = Path(self.tmp.name) / "out"
        target = out_dir / "note.txt"
        mock = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="write_file",
                            arguments={
                                "path": str(target),
                                "content": "محتوى معتمَد",
                            },
                        )
                    ]
                ),
                ChatResult(text="تمّ الحفظ"),
            ]
        )
        runner = self.make_runner(mock=mock)
        bot_id = runner.call(lambda e: e.create_bot("كاتب", "openrouter"))
        app = KrouchiApp(self.root, runner, self.bridge)
        self.pump_until(lambda: app.bots_list.size() == 1)
        app.select_bot(bot_id)
        app.entry_var.set("احفظ ملاحظة")
        app.send_current()
        self.pump_until(lambda: app._active_approval is not None)
        dialog = app._active_approval
        self.assertEqual(dialog.request.action, "write_file")
        dialog.allow_button.invoke()
        self.pump_until(lambda: not app._working and target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "محتوى معتمَد")
        audit = runner.call(lambda e: e.db.get_audit(bot_id=bot_id))
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["decision"], "allowed")

    def test_approval_card_close_denies_and_nothing_executes(self):
        target = Path(self.tmp.name) / "never.txt"
        mock = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="write_file",
                            arguments={"path": str(target), "content": "x"},
                        )
                    ]
                ),
                ChatResult(text="حسناً"),
            ]
        )
        runner = self.make_runner(mock=mock)
        bot_id = runner.call(lambda e: e.create_bot("كاتب", "openrouter"))
        app = KrouchiApp(self.root, runner, self.bridge)
        self.pump_until(lambda: app.bots_list.size() == 1)
        app.select_bot(bot_id)
        app.entry_var.set("اكتب")
        app.send_current()
        self.pump_until(lambda: app._active_approval is not None)
        app._active_approval.deny_button.invoke()
        self.pump_until(lambda: not app._working)
        self.assertFalse(target.exists())
        audit = runner.call(lambda e: e.db.get_audit(bot_id=bot_id))
        self.assertEqual(audit[0]["decision"], "denied")


# ======================================================================
# نافذة سجلّ التدقيق
# ======================================================================
class TestAuditWindow(GuiFixture):
    def test_audit_rows_rendered(self):
        runner = self.make_runner()
        bot_id = runner.call(
            lambda e: e.create_bot("حرّ", "openrouter", approval_mode="full")
        )
        path = str(Path(self.tmp.name) / "a.txt")
        runner.call(
            lambda e: e.perform_action(
                bot_id, "write_file", {"path": path, "content": "y"}
            )
        )
        window = AuditWindow(self.root, runner)
        self.addCleanup(window.top.destroy)
        self.pump_until(lambda: window.rows_loaded)
        children = window.tree.get_children()
        self.assertEqual(len(children), 1)
        values = window.tree.item(children[0], "values")
        self.assertIn("سماح", str(values))
        self.assertIn("كتابة ملف", str(values))


# ======================================================================
# نافذة ربط الهاتف (خادم المرافقة)
# ======================================================================
class TestPhoneLinkDialog(GuiFixture):
    def make_dialog(self):
        runner = self.make_runner()
        server = CompanionServer(
            engine_call=runner.call_blocking,
            registry=self.bridge.registry,
            token="tok-1234567890",
            port=0,
        )
        self.addCleanup(server.stop)
        dialog = PhoneLinkDialog(self.root, runner, server)
        self.addCleanup(dialog.top.destroy)
        return dialog, server

    def test_start_stop_buttons_drive_server(self):
        dialog, server = self.make_dialog()
        self.assertFalse(server.running)
        self.assertIn("متوقّف", dialog.status_label.cget("text"))
        dialog.start_server()
        self.assertTrue(server.running)
        self.assertIn("يعمل", dialog.status_label.cget("text"))
        self.assertGreater(server.port, 0)
        dialog.stop_server()
        self.assertFalse(server.running)
        self.assertIn("متوقّف", dialog.status_label.cget("text"))

    def test_regenerate_token_updates_dialog_and_server(self):
        dialog, server = self.make_dialog()
        old = dialog.token_var.get()
        dialog.regenerate()
        self.pump_until(lambda: dialog.token_var.get() != old)
        self.assertEqual(server.token, dialog.token_var.get())
        self.assertGreaterEqual(len(dialog.token_var.get()), 12)
        # والرمز الجديد محفوظ في إعدادات قاعدة البيانات أيضاً
        saved = dialog.runner.call(
            lambda e: e.db.get_setting("companion_token", "")
        )
        self.assertEqual(saved, dialog.token_var.get())

    def test_autostart_checkbox_persists_setting(self):
        dialog, server = self.make_dialog()
        dialog.autostart_var.set(True)
        dialog._save_autostart()
        self.pump_until(
            lambda: dialog.runner.call(
                lambda e: e.db.get_setting("companion_autostart", "")
            )
            == "1"
        )

    def test_control_toggle_persists_server_format(self):
        dialog, server = self.make_dialog()
        # غياب الإعداد = مفعَّل عند الخادم وعند الحوار معاً (الافتراضي).
        self.assertTrue(server.is_control_enabled())
        self.pump_until(lambda: dialog.control_var.get() is True)
        dialog.control_var.set(False)
        dialog._save_control()
        self.pump_until(
            lambda: dialog.runner.call(
                lambda e: e.db.get_setting("control_enabled", "")
            )
            == "false"
        )
        # الخادم يقرأ القيمة المكتوبة بمنطقه نفسه: معطَّل.
        self.assertFalse(server.is_control_enabled())
        dialog.control_var.set(True)
        dialog._save_control()
        self.pump_until(
            lambda: dialog.runner.call(
                lambda e: e.db.get_setting("control_enabled", "")
            )
            == "true"
        )
        self.assertTrue(server.is_control_enabled())

    def test_control_toggle_reflects_saved_disabled_value(self):
        runner = self.make_runner()
        runner.call(
            lambda e: e.db.set_setting("control_enabled", "false")
        )
        server = CompanionServer(
            engine_call=runner.call_blocking,
            registry=self.bridge.registry,
            token="tok-1234567890",
            port=0,
        )
        self.addCleanup(server.stop)
        dialog = PhoneLinkDialog(self.root, runner, server)
        self.addCleanup(dialog.top.destroy)
        self.pump_until(lambda: dialog.control_var.get() is False)

    def test_screen_indicator_follows_server_viewers(self):
        dialog, server = self.make_dialog()
        self.assertEqual(dialog.screen_label.cget("text"), "")
        server._note_screen_stream(1)
        dialog._refresh_screen_indicator()
        self.assertIn("الشاشة مشتركة الآن", dialog.screen_label.cget("text"))
        server._note_screen_stream(-1)
        dialog._refresh_screen_indicator()
        self.assertEqual(dialog.screen_label.cget("text"), "")

    def test_tasks_button_opens_tasks_window(self):
        dialog, server = self.make_dialog()
        window = dialog.open_tasks()
        self.addCleanup(window.top.destroy)
        self.pump_until(lambda: window.rows_loaded)
        self.assertEqual(window.empty_label.cget("text"), "لا مهام بعد")


# ======================================================================
# وسم عناوين Tailscale وتفسير إعداد التحكم (دوال نقية — بلا شاشة)
# ======================================================================
class TestIpLabel(unittest.TestCase):
    def test_tailscale_range_is_labeled(self):
        self.assertEqual(ip_label("100.64.0.1"), "100.64.0.1 (Tailscale)")
        self.assertEqual(
            ip_label("100.127.255.254"), "100.127.255.254 (Tailscale)"
        )
        self.assertEqual(ip_label("100.100.1.1"), "100.100.1.1 (Tailscale)")

    def test_other_addresses_stay_plain(self):
        for ip in (
            "100.63.255.255",  # أسفل النطاق مباشرة
            "100.128.0.1",     # أعلى النطاق مباشرة
            "192.168.1.5",
            "10.0.0.3",
            "172.16.0.2",
            "8.8.8.8",
        ):
            self.assertEqual(ip_label(ip), ip)

    def test_garbage_stays_plain(self):
        self.assertEqual(ip_label("not-an-ip"), "not-an-ip")
        self.assertEqual(ip_label(""), "")


class TestControlSettingEnabled(unittest.TestCase):
    def test_mirrors_server_logic(self):
        self.assertTrue(control_setting_enabled(None))      # غياب = افتراضي
        self.assertTrue(control_setting_enabled("true"))
        self.assertTrue(control_setting_enabled("1"))
        self.assertTrue(control_setting_enabled("yes"))
        for raw in ("false", "0", "no", "off", " FALSE ", "Off"):
            self.assertFalse(control_setting_enabled(raw), raw)


# ======================================================================
# نافذة مهام البوتات
# ======================================================================
class TestTasksWindow(GuiFixture):
    def seed_task(self, runner, title="مهمة تجريبية", prompt="اكتب تقريراً",
                  status="queued"):
        bot_id = runner.call(lambda e: e.create_bot("منفّذ", "openrouter"))
        db_path = runner.call(lambda e: str(e.db.path))
        store = TaskStore(db_path)
        try:
            task = store.create_task(bot_id, title, prompt)
            if status != "queued":
                store.update_task(task["id"], status=status)
            return task["id"]
        finally:
            store.close()

    def stored_status(self, runner, task_id):
        db_path = runner.call(lambda e: str(e.db.path))
        store = TaskStore(db_path)
        try:
            task = store.get_task(task_id)
            return task["status"] if task else None
        finally:
            store.close()

    def test_renders_seeded_task_with_localized_status(self):
        runner = self.make_runner()
        self.seed_task(runner)
        window = TasksWindow(self.root, runner)
        self.addCleanup(window.top.destroy)
        self.pump_until(lambda: window.rows_loaded)
        children = window.tree.get_children()
        self.assertEqual(len(children), 1)
        values = window.tree.item(children[0], "values")
        self.assertIn("مهمة تجريبية", str(values))
        self.assertIn("منفّذ", str(values))       # اسم البوت من الوصل
        self.assertIn("في الانتظار", str(values))  # queued مترجمة
        self.assertEqual(window.empty_label.cget("text"), "")
        # تحديد الصفّ يعرض التعليمة في لوحة التفاصيل ويُفعّل الإلغاء.
        window.tree.selection_set(children[0])
        window._on_select()
        self.assertIn("اكتب تقريراً", window.prompt_text.get("1.0", "end"))
        self.assertEqual(str(window.cancel_button.cget("state")), "normal")

    def test_empty_state_text(self):
        runner = self.make_runner()
        window = TasksWindow(self.root, runner)
        self.addCleanup(window.top.destroy)
        self.pump_until(lambda: window.rows_loaded)
        self.assertEqual(window.tree.get_children(), ())
        self.assertEqual(window.empty_label.cget("text"), "لا مهام بعد")

    def test_cancel_button_uses_store_path_without_manager(self):
        runner = self.make_runner()
        task_id = self.seed_task(runner)
        window = TasksWindow(self.root, runner)  # بلا خادم: مسار المخزن
        self.addCleanup(window.top.destroy)
        self.pump_until(lambda: window.rows_loaded)
        window.tree.selection_set(window.tree.get_children()[0])
        window._on_select()
        window.cancel_task()
        self.pump_until(
            lambda: self.stored_status(runner, task_id) == "cancelled"
        )
        # والقائمة المحدّثة تُظهر الحالة الجديدة مترجمة.
        self.pump_until(
            lambda: any(
                "أُلغيت" in str(window.tree.item(c, "values"))
                for c in window.tree.get_children()
            )
        )

    def test_cancel_button_invokes_server_task_manager(self):
        runner = self.make_runner()
        task_id = self.seed_task(runner)
        calls = []

        class _StubManager:
            def cancel(self, tid):
                calls.append(tid)
                return "ok"

        stub_server = types.SimpleNamespace(task_manager=_StubManager())
        window = TasksWindow(self.root, runner, server=stub_server)
        self.addCleanup(window.top.destroy)
        self.pump_until(lambda: window.rows_loaded)
        window.tree.selection_set(window.tree.get_children()[0])
        window._on_select()
        window.cancel_task()
        # نقطة الدخول نفسها التي تستعملها نقطة إلغاء الخادم، بنفس المعرّف.
        self.pump_until(lambda: calls == [task_id])

    def test_cancel_button_disabled_for_final_task(self):
        runner = self.make_runner()
        self.seed_task(runner, status="done")
        window = TasksWindow(self.root, runner)
        self.addCleanup(window.top.destroy)
        self.pump_until(lambda: window.rows_loaded)
        children = window.tree.get_children()
        self.assertEqual(len(children), 1)
        self.assertIn(
            "اكتملت", str(window.tree.item(children[0], "values"))
        )
        window.tree.selection_set(children[0])
        window._on_select()
        self.assertEqual(
            str(window.cancel_button.cget("state")), "disabled"
        )


# ======================================================================
# تبديل اللغة (العربية / الإنجليزية) في النافذة الرئيسية
# ======================================================================
class TestLanguageSwitch(GuiFixture):
    def setUp(self):
        super().setUp()
        self.addCleanup(i18n.set_lang, "ar")

    def test_default_arabic_sidebar_right(self):
        runner = self.make_runner()
        app = KrouchiApp(self.root, runner, self.bridge)
        self.assertEqual(i18n.get_lang(), "ar")
        self.assertEqual(app.send_button.cget("text"), "إرسال")
        self.assertEqual(app.sidebar_frame.pack_info()["side"], "right")

    def test_window_in_english_from_saved_setting(self):
        runner = self.make_runner()
        runner.call(lambda e: e.db.set_setting("ui_lang", "en"))
        runner.call(lambda e: e.create_bot("مساعد", "openrouter"))
        app = KrouchiApp(self.root, runner, self.bridge)
        self.pump_until(lambda: app.bots_list.size() == 1)
        self.assertEqual(i18n.get_lang(), "en")
        self.assertEqual(app.send_button.cget("text"), "Send")
        self.assertEqual(app.sidebar_frame.pack_info()["side"], "left")
        self.assertIn("Approval:", app.header_label.cget("text"))

    def test_switch_rebuilds_persists_and_server_survives(self):
        runner = self.make_runner()
        bot_id = runner.call(lambda e: e.create_bot("ثابت", "openrouter"))
        server = CompanionServer(
            engine_call=runner.call_blocking,
            registry=self.bridge.registry,
            token="tok-1234567890",
            port=0,
        )
        server.start()
        self.addCleanup(server.stop)
        app = KrouchiApp(self.root, runner, self.bridge, server=server)
        self.pump_until(lambda: app.bots_list.size() == 1)
        self.assertEqual(app.send_button.cget("text"), "إرسال")
        self.assertEqual(app.sidebar_frame.pack_info()["side"], "right")

        old_listbox = app.bots_list
        app.switch_language("en")
        # أعيد بناء الويدجتات نفسها (قائمة جديدة) دون إعادة تشغيل العملية.
        self.assertIsNot(app.bots_list, old_listbox)
        self.assertEqual(app.send_button.cget("text"), "Send")
        self.assertEqual(app.sidebar_frame.pack_info()["side"], "left")
        self.assertTrue(server.running)  # الخادم لم يُلمَس
        self.pump_until(lambda: app.bots_list.size() == 1)
        self.assertEqual(app.selected_bot_id, bot_id)  # التحديد محفوظ
        self.pump_until(
            lambda: runner.call(lambda e: e.db.get_setting("ui_lang", ""))
            == "en"
        )

        app.switch_language("ar")
        self.assertEqual(app.send_button.cget("text"), "إرسال")
        self.assertEqual(app.sidebar_frame.pack_info()["side"], "right")
        self.assertTrue(server.running)
        self.pump_until(
            lambda: runner.call(lambda e: e.db.get_setting("ui_lang", ""))
            == "ar"
        )

    def test_switch_to_same_or_unknown_language_is_noop(self):
        runner = self.make_runner()
        app = KrouchiApp(self.root, runner, self.bridge)
        same_listbox = app.bots_list
        app.switch_language("ar")   # نفس اللغة الحالية
        app.switch_language("fr")   # لغة غير مدعومة أصلاً
        self.assertIs(app.bots_list, same_listbox)
        self.assertEqual(i18n.get_lang(), "ar")


if __name__ == "__main__":
    unittest.main()
