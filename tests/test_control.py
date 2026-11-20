"""اختبارات تحكّم الهاتف بالحاسوب (الإصدار 3.2): حالة، ملفات، أوامر،
طاقة، طباعة، رفع، حافظة — HTTP حقيقي، ومنفّذات المنصّة وهمية بالحقن
فلا تُطبع ورقة ولا تُلمس حافظة ولا يُطفأ جهاز في الاختبار أبداً.

أفعال التحكّم الكتابية تمرّ بوسيط المحرّك وسجلّه المشترك: كل اختبار
موافقة يشغّل الطلب في خيط، ينتظر ظهوره في /api/approvals، ثم يحسمه
من «الهاتف» — نفس دورة موافقات المحادثة.
"""

import base64
import ctypes
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock as umock
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_server import ServerFixture  # noqa: E402

from krouchi_dz import control  # noqa: E402


class ControlFixture(ServerFixture):
    """خادم بجذر تحكّم مؤقت ومنفّذات وهمية مسجِّلة لنداءاتها."""

    def make_control_server(self, **kwargs):
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir(parents=True, exist_ok=True)
        self.calls = {
            "power": [], "open": [], "print": [], "clipboard_set": [],
            "volume": [], "window": [], "kill": [],
        }
        self.clipboard_text = ""
        kwargs.setdefault("control_root", self.root)
        kwargs.setdefault(
            "power_executor", lambda action: self.calls["power"].append(action)
        )
        kwargs.setdefault(
            "open_executor", lambda target: self.calls["open"].append(target)
        )
        kwargs.setdefault(
            "print_executor",
            lambda path, printer=None: self.calls["print"].append((path, printer)),
        )
        kwargs.setdefault(
            "printer_lister",
            lambda: [{"name": "طابعة المكتب", "is_default": True}],
        )
        kwargs.setdefault("clipboard_getter", lambda: self.clipboard_text)
        kwargs.setdefault(
            "clipboard_setter",
            lambda text: (
                self.calls["clipboard_set"].append(text),
                setattr(self, "clipboard_text", text),
            ),
        )
        kwargs.setdefault(
            "volume_executor", lambda action: self.calls["volume"].append(action)
        )
        kwargs.setdefault(
            "window_lister",
            lambda: [{"id": 101, "title": "المفكرة"}, {"id": 202, "title": "المتصفح"}],
        )
        kwargs.setdefault(
            "window_executor",
            lambda wid, action: self.calls["window"].append((wid, action)),
        )
        kwargs.setdefault(
            "process_lister",
            lambda: [
                {"pid": 42, "name": "chrome", "mem_mb": 512.5},
                {"pid": 7, "name": "python", "mem_mb": 64.0},
            ],
        )
        kwargs.setdefault(
            "process_killer", lambda pid: self.calls["kill"].append(pid)
        )
        return self.make_server(**kwargs)

    # -- دورة الموافقة عبر HTTP ----------------------------------------------
    def post_in_thread(self, path, body):
        holder = {}

        def run():
            holder["result"] = self.request("POST", path, body)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, holder

    def approve_pending(self, decision="approve"):
        item = self.wait_pending_http()
        status, _ = self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": decision}
        )
        self.assertEqual(status, 200)
        return item


class TestStatus(ControlFixture):
    def test_status_shape(self):
        self.make_control_server()
        status, data = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["app"], "Krouchi_DZ")
        self.assertEqual(data["version"], "3.4.0")
        self.assertTrue(data["os"])
        self.assertTrue(data["platform"])
        self.assertTrue(data["hostname"])
        self.assertTrue(data["home"])
        self.assertIn("uptime_s", data)
        self.assertIsInstance(data["disk"]["total_gb"], (int, float))
        self.assertIsInstance(data["disk"]["free_gb"], (int, float))
        self.assertTrue(
            data["ram_mb"] is None or isinstance(data["ram_mb"], int)
        )


class TestFiles(ControlFixture):
    def setUp(self):
        super().setUp()
        self.make_control_server()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.txt").write_text("أهلا", encoding="utf-8")
        (self.root / "b.bin").write_bytes(b"\x00\x01\x02")

    def test_list_root_dirs_first(self):
        status, data = self.request("GET", "/api/files")
        self.assertEqual(status, 200)
        self.assertEqual(data["path"], str(self.root.resolve()))
        self.assertIsNone(data["parent"])
        kinds = [(e["name"], e["kind"]) for e in data["entries"]]
        self.assertEqual(kinds[0], ("docs", "dir"))
        self.assertEqual(kinds[1], ("b.bin", "file"))
        self.assertEqual(data["entries"][1]["size"], 3)
        self.assertIsNone(data["entries"][0]["size"])

    def test_list_subdir_and_parent(self):
        status, data = self.request(
            "GET", f"/api/files?path={quote(str(self.root / 'docs'))}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["parent"], str(self.root.resolve()))
        self.assertEqual([e["name"] for e in data["entries"]], ["a.txt"])

    def test_list_missing_is_404(self):
        status, _ = self.request(
            "GET", f"/api/files?path={quote(str(self.root / 'nope'))}"
        )
        self.assertEqual(status, 404)

    def test_traversal_is_403(self):
        outside = Path(self.tmp.name)  # فوق الجذر
        for raw in (str(outside), "..", "../..", "/etc"):
            status, _ = self.request(
                "GET", f"/api/files?path={quote(raw)}"
            )
            self.assertEqual(status, 403, raw)

    def test_file_download(self):
        status, data = self.request(
            "GET", f"/api/file?path={quote(str(self.root / 'b.bin'))}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["name"], "b.bin")
        self.assertEqual(data["size"], 3)
        self.assertEqual(base64.b64decode(data["content_b64"]), b"\x00\x01\x02")

    def test_file_missing_is_404(self):
        status, _ = self.request(
            "GET", f"/api/file?path={quote(str(self.root / 'ghost.txt'))}"
        )
        self.assertEqual(status, 404)


class TestFileTooBig(ControlFixture):
    def test_download_over_cap_is_413(self):
        self.make_control_server(file_max_bytes=4)
        big = self.root / "big.bin"
        big.write_bytes(b"0123456789")
        status, _ = self.request(
            "GET", f"/api/file?path={quote(str(big))}"
        )
        self.assertEqual(status, 413)


class TestRunCommand(ControlFixture):
    def test_run_approved_executes(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/run", {"command": "echo krouchi-marker"}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "run_command")
        self.assertEqual(item["bot_name"], "تحكّم الهاتف")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertEqual(data["exit"], 0)
        self.assertIn("krouchi-marker", data["stdout"])
        self.assertFalse(data["timed_out"])

    def test_run_denied_is_403(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/run", {"command": "echo never"}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "denied")

    def test_run_bad_body_is_400(self):
        self.make_control_server()
        status, _ = self.request("POST", "/api/run", {"command": "  "})
        self.assertEqual(status, 400)


class TestOpenAndPower(ControlFixture):
    def test_open_approved(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/open", {"target": "https://example.test"}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "open_target")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.calls["open"], ["https://example.test"])

    def test_open_denied(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/open", {"target": "https://example.test"}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, _ = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(self.calls["open"], [])

    def test_power_approved_calls_executor_once(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/power", {"action": "shutdown"}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "power")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["scheduled_in_s"], 60)
        self.assertEqual(self.calls["power"], ["shutdown"])

    def test_power_denied_never_calls_executor(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/power", {"action": "restart"}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "denied")
        self.assertEqual(self.calls["power"], [])

    def test_power_bad_action_is_400(self):
        self.make_control_server()
        status, _ = self.request("POST", "/api/power", {"action": "explode"})
        self.assertEqual(status, 400)


class TestPrintersAndPrint(ControlFixture):
    def test_printers_shape_with_fake_lister(self):
        self.make_control_server()
        status, data = self.request("GET", "/api/printers")
        self.assertEqual(status, 200)
        self.assertEqual(
            data["printers"], [{"name": "طابعة المكتب", "is_default": True}]
        )

    def test_print_approved(self):
        self.make_control_server()
        doc = self.root / "doc.txt"
        doc.write_text("للطباعة", encoding="utf-8")
        thread, holder = self.post_in_thread(
            "/api/print", {"path": str(doc), "printer": "طابعة المكتب"}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "print_file")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(
            self.calls["print"], [(str(doc.resolve()), "طابعة المكتب")]
        )

    def test_print_denied(self):
        self.make_control_server()
        doc = self.root / "doc.txt"
        doc.write_text("x", encoding="utf-8")
        thread, holder = self.post_in_thread(
            "/api/print", {"path": str(doc)}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, _ = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(self.calls["print"], [])

    def test_print_outside_root_is_403_without_approval(self):
        self.make_control_server()
        outside = Path(self.tmp.name) / "secret.txt"
        outside.write_text("سر", encoding="utf-8")
        status, _ = self.request("POST", "/api/print", {"path": str(outside)})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls["print"], [])


class TestUpload(ControlFixture):
    def test_upload_approved_writes_bytes_and_creates_dirs(self):
        self.make_control_server()
        payload = base64.b64encode(b"hello-upload").decode("ascii")
        target = self.root / "sub" / "dir" / "up.bin"
        thread, holder = self.post_in_thread(
            "/api/upload", {"path": str(target), "content_b64": payload}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "upload_file")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["size"], len(b"hello-upload"))
        self.assertEqual(target.read_bytes(), b"hello-upload")

    def test_upload_denied_writes_nothing(self):
        self.make_control_server()
        payload = base64.b64encode(b"nope").decode("ascii")
        target = self.root / "no.bin"
        thread, holder = self.post_in_thread(
            "/api/upload", {"path": str(target), "content_b64": payload}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, _ = holder["result"]
        self.assertEqual(status, 403)
        self.assertFalse(target.exists())

    def test_upload_traversal_is_403(self):
        self.make_control_server()
        payload = base64.b64encode(b"evil").decode("ascii")
        status, _ = self.request(
            "POST",
            "/api/upload",
            {"path": "../evil.bin", "content_b64": payload},
        )
        self.assertEqual(status, 403)
        self.assertFalse((Path(self.tmp.name) / "evil.bin").exists())

    def test_upload_oversize_is_413(self):
        self.make_control_server(upload_max_bytes=4)
        payload = base64.b64encode(b"0123456789").decode("ascii")
        status, _ = self.request(
            "POST",
            "/api/upload",
            {"path": str(self.root / "big.bin"), "content_b64": payload},
        )
        self.assertEqual(status, 413)

    def test_upload_bad_base64_is_400(self):
        self.make_control_server()
        status, _ = self.request(
            "POST",
            "/api/upload",
            {"path": str(self.root / "x.bin"), "content_b64": "!!!"},
        )
        self.assertEqual(status, 400)


class TestClipboard(ControlFixture):
    def test_get_clipboard_with_fake(self):
        self.make_control_server()
        self.clipboard_text = "نص من الحاسوب"
        status, data = self.request("GET", "/api/clipboard")
        self.assertEqual(status, 200)
        self.assertEqual(data["text"], "نص من الحاسوب")

    def test_set_clipboard_approved(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/clipboard", {"text": "انسخني"}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "set_clipboard")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.calls["clipboard_set"], ["انسخني"])

    def test_set_clipboard_denied(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/clipboard", {"text": "لا"}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, _ = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(self.calls["clipboard_set"], [])

    def test_clipboard_helpers_with_fake_runner(self):
        def fake_get(argv):
            return 0, "من الحافظة"

        with umock.patch.object(control, "IS_WINDOWS", True):
            self.assertEqual(control.get_clipboard(runner=fake_get), "من الحافظة")
            seen = {}

            def fake_set(argv, input_text=None):
                seen["argv"] = argv
                seen["input"] = input_text
                return 0, ""

            control.set_clipboard("جديد", runner=fake_set)
            self.assertEqual(seen["input"], "جديد")


class TestPowerExtended(ControlFixture):
    """القفل والسكون والخروج: فورية بعد الموافقة (scheduled_in_s = 0)."""

    def run_power(self, action, decision):
        thread, holder = self.post_in_thread("/api/power", {"action": action})
        item = self.approve_pending(decision)
        self.assertEqual(item["tool"], "power")
        thread.join(15.0)
        return holder["result"]

    def test_lock_approved_immediate(self):
        self.make_control_server()
        status, data = self.run_power("lock", "approve")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["scheduled_in_s"], 0)
        self.assertEqual(self.calls["power"], ["lock"])

    def test_sleep_approved_immediate(self):
        self.make_control_server()
        status, data = self.run_power("sleep", "approve")
        self.assertEqual(status, 200)
        self.assertEqual(data["scheduled_in_s"], 0)
        self.assertEqual(self.calls["power"], ["sleep"])

    def test_logoff_denied_never_executes(self):
        self.make_control_server()
        status, data = self.run_power("logoff", "deny")
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "denied")
        self.assertEqual(self.calls["power"], [])


class TestVolume(ControlFixture):
    def test_volume_up_ok_without_approval(self):
        self.make_control_server()
        status, data = self.request("POST", "/api/volume", {"action": "up"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.calls["volume"], ["up"])
        # بلا وسيط: لا طلب موافقة معلّقاً خُلّف وراءه
        _, pending = self.request("GET", "/api/approvals")
        self.assertEqual(pending["pending"], [])

    def test_volume_mute_and_bad_action(self):
        self.make_control_server()
        status, _ = self.request("POST", "/api/volume", {"action": "mute"})
        self.assertEqual(status, 200)
        status, _ = self.request("POST", "/api/volume", {"action": "max"})
        self.assertEqual(status, 400)
        self.assertEqual(self.calls["volume"], ["mute"])


class TestWindowsAndProcesses(ControlFixture):
    def test_windows_list_shape(self):
        self.make_control_server()
        status, data = self.request("GET", "/api/windows")
        self.assertEqual(status, 200)
        self.assertEqual(
            data["windows"],
            [{"id": 101, "title": "المفكرة"}, {"id": 202, "title": "المتصفح"}],
        )

    def test_list_windows_non_windows_is_empty(self):
        if not control.IS_WINDOWS:
            self.assertEqual(control.list_windows(), [])

    def test_window_control_approved(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/window", {"id": 101, "action": "minimize"}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "window_control")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.calls["window"], [(101, "minimize")])

    def test_window_close_denied(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/window", {"id": "202", "action": "close"}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, _ = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(self.calls["window"], [])

    def test_window_bad_action_is_400(self):
        self.make_control_server()
        status, _ = self.request(
            "POST", "/api/window", {"id": 101, "action": "explode"}
        )
        self.assertEqual(status, 400)

    def test_processes_shape(self):
        self.make_control_server()
        status, data = self.request("GET", "/api/processes")
        self.assertEqual(status, 200)
        self.assertEqual(data["processes"][0]["pid"], 42)
        self.assertEqual(data["processes"][0]["name"], "chrome")
        self.assertEqual(data["processes"][0]["mem_mb"], 512.5)

    def test_list_processes_ps_runner_parsing(self):
        def fake_runner(argv):
            self.assertEqual(argv[0], "ps")
            return 0, "  123 firefox        204800\n    9 systemd           10240\n"

        with umock.patch.object(control, "IS_WINDOWS", False):
            processes = control.list_processes(runner=fake_runner)
        self.assertEqual(processes[0], {"pid": 123, "name": "firefox", "mem_mb": 200.0})
        self.assertEqual(processes[1]["pid"], 9)

    def test_kill_process_approved(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/process/kill", {"pid": 42}
        )
        item = self.approve_pending("approve")
        self.assertEqual(item["tool"], "kill_process")
        thread.join(15.0)
        status, data = holder["result"]
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.calls["kill"], [42])

    def test_kill_process_denied(self):
        self.make_control_server()
        thread, holder = self.post_in_thread(
            "/api/process/kill", {"pid": "42"}
        )
        self.approve_pending("deny")
        thread.join(15.0)
        status, _ = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(self.calls["kill"], [])

    def test_kill_bad_pid_is_400(self):
        self.make_control_server()
        status, _ = self.request("POST", "/api/process/kill", {"pid": -3})
        self.assertEqual(status, 400)


class TestScreenshot(ControlFixture):
    def test_screenshot_branch(self):
        self.make_control_server()
        status, data = self.request("GET", "/api/screenshot")
        # لينكس الاختبار: 501 متوقّعة؛ منصّة قادرة: 200 بصورة وشكل
        self.assertIn(status, (200, 501))
        if status == 200:
            self.assertIn("image_b64", data)
            self.assertIn("format", data)
        else:
            self.assertIn("error", data)


class TestControlDisabled(ControlFixture):
    def test_disabled_control_family_is_403_but_status_and_tasks_live(self):
        self.make_control_server()
        self.gateway.call(
            lambda e: e.db.set_setting("control_enabled", "false")
        )
        for method, path in (
            ("GET", "/api/files"),
            ("GET", "/api/printers"),
            ("GET", "/api/clipboard"),
            ("GET", "/api/windows"),
            ("GET", "/api/processes"),
            ("POST", "/api/run"),
            ("POST", "/api/volume"),
        ):
            body = (
                {"command": "echo x", "action": "up"}
                if method == "POST"
                else None
            )
            status, data = self.request(method, path, body)
            self.assertEqual(status, 403, path)
            self.assertEqual(data["error"], "control disabled")
        status, _ = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        status, data = self.request("GET", "/api/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(data["tasks"], [])


class TestScreenshotPaths(unittest.TestCase):
    """لقطة الشاشة (3.4): Pillow أولاً على ويندوز، وPowerShell احتياطياً."""

    PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png"

    def _pil_modules(self, grab):
        pil = types.ModuleType("PIL")
        grab_module = types.ModuleType("PIL.ImageGrab")
        grab_module.grab = grab
        pil.ImageGrab = grab_module
        return {"PIL": pil, "PIL.ImageGrab": grab_module}

    def test_pillow_path_returns_png_and_never_touches_powershell(self):
        class FakeImage:
            def save(self, buffer, format=None):
                buffer.write(TestScreenshotPaths.PNG_BYTES)

        def forbidden_run(*args, **kwargs):
            raise AssertionError("PowerShell يجب ألا يعمل ما دامت Pillow تعمل")

        modules = self._pil_modules(lambda: FakeImage())
        fake_subprocess = types.SimpleNamespace(run=forbidden_run)
        with umock.patch.dict(sys.modules, modules), \
            umock.patch.object(control, "IS_WINDOWS", True), \
            umock.patch.object(control, "subprocess", fake_subprocess):
            result = control.take_screenshot()
        self.assertEqual(result, (self.PNG_BYTES, "png"))

    def test_powershell_fallback_when_pillow_missing(self):
        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            tmp = Path(tempfile.gettempdir()) / "krouchi_screenshot.png"
            tmp.write_bytes(b"powershell-png")
            return types.SimpleNamespace(returncode=0)

        blocked = {"PIL": None, "PIL.ImageGrab": None}
        fake_subprocess = types.SimpleNamespace(run=fake_run)
        with umock.patch.dict(sys.modules, blocked), \
            umock.patch.object(control, "IS_WINDOWS", True), \
            umock.patch.object(control, "subprocess", fake_subprocess):
            result = control.take_screenshot()
        self.assertEqual(result, (b"powershell-png", "png"))
        script = captured["argv"][-1]
        self.assertIn("Bitmap($b.Width, $b.Height)", script)
        self.assertNotIn("Bitmap $b.Width", script)

    def test_powershell_fallback_when_imagegrab_raises(self):
        def bad_grab():
            raise RuntimeError("لا سطح مكتب")

        def fake_run(argv, **kwargs):
            tmp = Path(tempfile.gettempdir()) / "krouchi_screenshot.png"
            tmp.write_bytes(b"fallback-png")
            return types.SimpleNamespace(returncode=0)

        modules = self._pil_modules(bad_grab)
        fake_subprocess = types.SimpleNamespace(run=fake_run)
        with umock.patch.dict(sys.modules, modules), \
            umock.patch.object(control, "IS_WINDOWS", True), \
            umock.patch.object(control, "subprocess", fake_subprocess):
            result = control.take_screenshot()
        self.assertEqual(result, (b"fallback-png", "png"))

    def test_non_windows_returns_none(self):
        with umock.patch.object(control, "IS_WINDOWS", False):
            self.assertIsNone(control.take_screenshot())


class TestListProcessesTasklist(unittest.TestCase):
    """عمليات ويندوز (3.4): tasklist CSV بدل PowerShell."""

    CSV = (
        '"chrome.exe","1234","Console","1","1,234,567 K"\r\n'
        '"svchost.exe","888","Services","0","12,340 K"\r\n'
        '"malformed row without commas"\r\n'
        '"bad.exe","notapid","Console","1","5,000 K"\r\n'
        '"tiny.exe","55","Console","1","512 K"\r\n'
    )

    def runner(self, argv):
        self.assertEqual(argv, ["tasklist", "/FO", "CSV", "/NH"])
        return 0, self.CSV

    def test_parsing_sorting_and_malformed_skipped(self):
        with umock.patch.object(control, "IS_WINDOWS", True):
            processes = control.list_processes(runner=self.runner)
        self.assertEqual(
            processes,
            [
                {"pid": 1234, "name": "chrome.exe",
                 "mem_mb": round(1234567 / 1024, 1)},
                {"pid": 888, "name": "svchost.exe",
                 "mem_mb": round(12340 / 1024, 1)},
                {"pid": 55, "name": "tiny.exe", "mem_mb": 0.5},
            ],
        )

    def test_limit_caps_after_sorting(self):
        with umock.patch.object(control, "IS_WINDOWS", True):
            processes = control.list_processes(runner=self.runner, limit=2)
        self.assertEqual([p["pid"] for p in processes], [1234, 888])


class TestPrintersParsing(unittest.TestCase):
    """طابعات ويندوز (3.4): فكّ سجلّات PRINTER_INFO_2 من مخزن ctypes."""

    def test_parse_records_from_fabricated_buffer(self):
        names = ["HP Laser", "Brother DCP"]
        name_buffers = [ctypes.create_unicode_buffer(n) for n in names]
        entries = (control._PrinterInfo2 * len(names))()
        for entry, name_buffer in zip(entries, name_buffers):
            entry.pPrinterName = ctypes.addressof(name_buffer)
        printers = control._parse_printer_records(
            entries, len(names), "Brother DCP"
        )
        self.assertEqual(
            printers,
            [
                {"name": "HP Laser", "is_default": False},
                {"name": "Brother DCP", "is_default": True},
            ],
        )

    def test_parse_records_zero_count_is_empty(self):
        self.assertEqual(control._parse_printer_records(None, 0), [])

    def test_list_printers_posix_lpstat_unchanged(self):
        def fake_runner(argv):
            if argv[1] == "-a":
                return 0, (
                    "HP accepting requests since Tue\n"
                    "Brother accepting requests since Tue\n"
                )
            return 0, "system default destination: HP\n"

        with umock.patch.object(control, "IS_WINDOWS", False), \
            umock.patch.object(
                control.shutil, "which", return_value="/usr/bin/lpstat"
            ):
            printers = control.list_printers(runner=fake_runner)
        self.assertEqual(
            printers,
            [
                {"name": "HP", "is_default": True},
                {"name": "Brother", "is_default": False},
            ],
        )


if __name__ == "__main__":
    unittest.main()
