"""اختبارات خادم مرافقة الهاتف: HTTP حقيقي على مقبس محلي، بلا شبكة خارجية.

المحرّك بمزوّد وهمي داخل EngineGateway (خيط مالك واحد كما في الإنتاج)،
والخادم على منفذ 0 (أي منفذ حرّ). تُغطّى: المصادقة بالرمز (401)،
ping، قائمة البوتات، المحادثة، وسجلّ المحادثة، ودورة الموافقة عن
بُعد كاملة: طلب أداة ← ظهوره في /api/approvals ← حسمه من «الهاتف»
(رفضاً فلا يُكتب الملف، أو قبولاً فيُكتب).
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import krouchi_dz
from krouchi_dz.broker import PendingApprovals
from krouchi_dz.engine import ChatEngine
from krouchi_dz.providers import ChatResult, MockProvider, ToolCall
from krouchi_dz.server import (
    PWA_FILES,
    CompanionServer,
    EngineGateway,
    find_pwa_dir,
    generate_token,
    get_or_create_token,
    regenerate_token,
)

TOKEN = "test-token-1234567890"


class ServerFixture(unittest.TestCase):
    """بوّابة محرّك (مزوّد وهمي) + خادم مرافقة يعمل على منفذ حرّ."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def make_server(self, mock=None, ask_timeout=10.0, **server_kwargs):
        self.mock = mock if mock is not None else MockProvider()
        self.registry = PendingApprovals()
        data_dir = Path(self.tmp.name) / "data"
        mock_ref = self.mock
        registry = self.registry

        def factory():
            return ChatEngine(
                data_dir,
                approval_registry=registry,
                ask_timeout=ask_timeout,
                provider_factory=lambda cfg, key: mock_ref,
            )

        self.gateway = EngineGateway(factory)
        self.addCleanup(self.gateway.close)
        # تحويل v3.4 (الواجهة المشتركة): المحادثة والمهام تُحسَمان
        # منها وحدها، فتضبط التركيبة واجهة صريحة في قاعدة البيانات
        # المشتركة (ترثها محرّكات المهام على مجلد البيانات نفسه).
        self.gateway.call(
            lambda e: e.set_shared_api("openrouter", "shared-model")
        )
        self.server = CompanionServer(
            engine_call=self.gateway.call,
            registry=self.registry,
            token=TOKEN,
            port=0,
            **server_kwargs,
        )
        self.server.start()
        self.addCleanup(self.server.stop)
        return self.server

    # -- عميل HTTP صغير ------------------------------------------------------
    def request(self, method, path, body=None, token=TOKEN, headers=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.port, timeout=15
        )
        hdrs = dict(headers or {})
        if token is not None:
            hdrs["X-Krouchi-Token"] = token
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, json.loads(raw.decode("utf-8"))

    def request_raw(self, method, path, token=None):
        """طلب بلا جسم وبلا رمز افتراضياً؛ يرجع (حالة، ترويسات، بايتات)."""
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.port, timeout=15
        )
        hdrs = {}
        if token is not None:
            hdrs["X-Krouchi-Token"] = token
        conn.request(method, path, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return resp.status, headers, raw

    def wait_pending_http(self, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, data = self.request("GET", "/api/approvals")
            self.assertEqual(status, 200)
            if data["pending"]:
                return data["pending"][0]
            time.sleep(0.02)
        self.fail("لم يظهر طلب موافقة عبر /api/approvals")


class TestAuthAndPing(ServerFixture):
    def test_missing_token_is_401(self):
        self.make_server()
        status, data = self.request("GET", "/api/ping", token=None)
        self.assertEqual(status, 401)
        self.assertIn("error", data)

    def test_wrong_token_is_401(self):
        self.make_server()
        status, _ = self.request("GET", "/api/bots", token="wrong-token-9999")
        self.assertEqual(status, 401)

    def test_ping_ok(self):
        self.make_server()
        status, data = self.request("GET", "/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["app"], "Krouchi_DZ")
        self.assertEqual(data["version"], krouchi_dz.__version__)

    def test_unknown_path_is_404(self):
        self.make_server()
        status, _ = self.request("GET", "/api/nope")
        self.assertEqual(status, 404)


class TestBotsAndChat(ServerFixture):
    def test_bots_list_shape(self):
        self.make_server()
        bot_id = self.gateway.call(
            lambda e: e.create_bot("مساعد", "openrouter", model="m-1")
        )
        status, data = self.request("GET", "/api/bots")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["bots"]), 1)
        bot = data["bots"][0]
        self.assertEqual(bot["id"], bot_id)
        self.assertEqual(bot["name"], "مساعد")
        # تحويل v3.4: الحمولة تعرض الواجهة المشتركة (مزوّد/نموذج
        # التركيبة) لا قيم البوت المخزَّنة («m-1») — الشكل لم يتغيّر.
        self.assertEqual(bot["provider"], "openrouter")
        self.assertEqual(bot["model"], "shared-model")
        self.assertEqual(bot["mode"], "ask")
        # أفاتار افتراضي لبوت جديد: "" (أحادي الحرف عند العميل).
        self.assertEqual(bot["avatar"], "")

    def test_bots_list_carries_gallery_avatar(self):
        self.make_server()
        self.gateway.call(
            lambda e: e.create_bot(
                "بصورة", "openrouter", avatar="bot_2.png"
            )
        )
        self.gateway.call(
            lambda e: e.create_bot(
                "قديم", "openrouter", avatar="🤖"
            )
        )
        status, data = self.request("GET", "/api/bots")
        self.assertEqual(status, 200)
        avatars = {b["name"]: b["avatar"] for b in data["bots"]}
        self.assertEqual(avatars["بصورة"], "bot_2.png")
        # القيمة القديمة تمرّ كما هي — العميل يفسّرها غير معرضية.
        self.assertEqual(avatars["قديم"], "🤖")

    def test_chat_roundtrip_and_history(self):
        self.make_server(MockProvider([ChatResult(text="ردّ الخادم")]))
        bot_id = self.gateway.call(
            lambda e: e.create_bot("محادث", "openrouter")
        )
        status, data = self.request(
            "POST", "/api/chat", {"bot_id": bot_id, "text": "سلام"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["reply"], "ردّ الخادم")
        self.assertNotIn("approval", data)  # لم يُطلب أي إجراء
        status, data = self.request("GET", f"/api/history?bot={bot_id}")
        self.assertEqual(status, 200)
        roles = [m["role"] for m in data["messages"]]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertEqual(data["messages"][0]["content"], "سلام")

    def test_chat_string_bot_id_accepted(self):
        """معرّف نصّي رقمي (من عميل أقدم) يُقبَل ولا يعيد 400."""
        self.make_server(MockProvider([ChatResult(text="ردّ الخادم")]))
        bot_id = self.gateway.call(
            lambda e: e.create_bot("محادث", "openrouter")
        )
        status, payload = self.request(
            "POST", "/api/chat", {"bot_id": str(bot_id), "text": "سلام"}
        )
        self.assertEqual(status, 200)
        self.assertIn("reply", payload)

    def test_chat_unknown_bot_is_404(self):
        self.make_server()
        status, _ = self.request(
            "POST", "/api/chat", {"bot_id": 4242, "text": "سلام"}
        )
        self.assertEqual(status, 404)

    def test_history_unknown_bot_is_404(self):
        self.make_server()
        status, _ = self.request("GET", "/api/history?bot=4242")
        self.assertEqual(status, 404)

    def test_chat_bad_body_is_400(self):
        self.make_server()
        status, _ = self.request("POST", "/api/chat", {"text": "بلا بوت"})
        self.assertEqual(status, 400)


class TestRemoteApprovals(ServerFixture):
    """الدورة الكاملة: أداة بنمط ask تُحسَم من الهاتف عبر HTTP."""

    def make_tool_server(self, target: Path):
        mock = MockProvider(
            [
                ChatResult(
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="write_file",
                            arguments={
                                "path": str(target),
                                "content": "من الهاتف",
                            },
                        )
                    ]
                ),
                ChatResult(text="انتهت المحادثة"),
            ]
        )
        self.make_server(mock)
        return self.gateway.call(
            lambda e: e.create_bot("كاتب", "openrouter")
        )

    def chat_in_thread(self, bot_id):
        holder = {}

        def run():
            holder["result"] = self.request(
                "POST", "/api/chat", {"bot_id": bot_id, "text": "احفظ"}
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, holder

    def test_remote_deny_file_not_written(self):
        target = Path(self.tmp.name) / "denied.txt"
        bot_id = self.make_tool_server(target)
        thread, holder = self.chat_in_thread(bot_id)
        item = self.wait_pending_http()
        self.assertEqual(item["bot_name"], "كاتب")
        self.assertEqual(item["tool"], "write_file")
        self.assertIn(str(target), item["summary"])
        self.assertIn("من الهاتف", item["summary"])
        self.assertTrue(item["created"])
        status, data = self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "deny"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["decision"], "denied")
        thread.join(10.0)
        status, payload = holder["result"]
        self.assertEqual(status, 200)
        self.assertEqual(payload["reply"], "انتهت المحادثة")
        self.assertEqual(payload["approval"], "denied")
        self.assertFalse(target.exists())
        # لم يبقَ شيء معلّقاً، والقرار مُدقّق في قاعدة الحاسوب
        _, data = self.request("GET", "/api/approvals")
        self.assertEqual(data["pending"], [])
        audit = self.gateway.call(lambda e: e.db.get_audit(bot_id=bot_id))
        self.assertEqual(audit[0]["decision"], "denied")

    def test_remote_approve_file_written(self):
        target = Path(self.tmp.name) / "approved.txt"
        bot_id = self.make_tool_server(target)
        thread, holder = self.chat_in_thread(bot_id)
        item = self.wait_pending_http()
        status, data = self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "approve"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["decision"], "approved")
        thread.join(10.0)
        status, payload = holder["result"]
        self.assertEqual(status, 200)
        self.assertEqual(payload["approval"], "approved")
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "من الهاتف")

    def test_resolve_unknown_item_is_404(self):
        self.make_server()
        status, _ = self.request(
            "POST", "/api/approvals/deadbeefdeadbeef", {"decision": "approve"}
        )
        self.assertEqual(status, 404)

    def test_resolve_bad_decision_is_400(self):
        target = Path(self.tmp.name) / "x.txt"
        bot_id = self.make_tool_server(target)
        thread, holder = self.chat_in_thread(bot_id)
        item = self.wait_pending_http()
        status, _ = self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "maybe"}
        )
        self.assertEqual(status, 400)
        # الطلب ما زال معلّقاً بعد القرار الفاسد — نحسمه رفضاً للإنهاء
        self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "deny"}
        )
        thread.join(10.0)
        self.assertIn("result", holder)


class TestTokenHelpers(ServerFixture):
    def test_get_or_create_persists_and_regenerate_rotates(self):
        self.make_server()
        first = self.gateway.call(lambda e: get_or_create_token(e.db))
        self.assertGreaterEqual(len(first), 12)
        again = self.gateway.call(lambda e: get_or_create_token(e.db))
        self.assertEqual(first, again)  # ثابت ما لم يُجدَّد
        rotated = self.gateway.call(lambda e: regenerate_token(e.db))
        self.assertNotEqual(first, rotated)

    def test_generate_token_length(self):
        self.assertGreaterEqual(len(generate_token()), 12)


class TestStaticShell(ServerFixture):
    """قشرة تطبيق الويب: تُخدَم بلا رمز، وبالقائمة البيضاء فقط."""

    def setUp(self):
        super().setUp()
        self.pwa_dir = find_pwa_dir()
        # شجرة المصدر تحمل مجلد pwa/ بجانب الحزمة — البحث يجب أن يجده
        self.assertIsNotNone(self.pwa_dir)

    def test_root_serves_index_without_token(self):
        self.make_server()
        status, headers, raw = self.request_raw("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], PWA_FILES["index.html"])
        self.assertEqual(raw, (self.pwa_dir / "index.html").read_bytes())

    def test_each_shell_file_both_shapes(self):
        self.make_server()
        for name, content_type in PWA_FILES.items():
            if name.startswith("avatars/"):
                # تحويل موثّق: صور المعرض لا تعيش داخل pwa/ في شجرة
                # المصدر (مكانها assets/avatars) فلا تُقرأ من مجلد
                # القشرة هنا — تُغطّيها TestAvatarStaticShell بمجلد
                # قشرة مؤقت يحملها، وتُخدَم هنا من المعرض عند الطلب.
                continue
            expected = (self.pwa_dir / name).read_bytes()
            for prefix in ("/", "/app/"):
                status, headers, raw = self.request_raw(
                    "GET", prefix + name
                )
                self.assertEqual(status, 200, prefix + name)
                self.assertEqual(
                    headers["content-type"], content_type, prefix + name
                )
                self.assertEqual(raw, expected, prefix + name)

    def test_service_worker_allowed_header(self):
        self.make_server()
        status, headers, _ = self.request_raw("GET", "/sw.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("service-worker-allowed"), "/")

    def test_traversal_attempts_are_404(self):
        self.make_server()
        for path in (
            "/../krouchi_dz/server.py",
            "/app/../../krouchi_dz/server.py",
            "/%2e%2e%2fserver.py",
            "/app/%2e%2e/sw.js/../server.py",
        ):
            status, _, _ = self.request_raw("GET", path)
            self.assertEqual(status, 404, path)

    def test_unlisted_or_unknown_paths_are_404(self):
        # README.md و tests_pwa.js موجودان فعلاً داخل مجلد pwa لكنهما
        # خارج القائمة البيضاء — يجب ألا يُخدَما أبداً.
        self.make_server()
        for path in ("/README.md", "/tests_pwa.js", "/nope.txt"):
            status, _, _ = self.request_raw("GET", path)
            self.assertEqual(status, 404, path)

    def test_api_still_requires_token_with_shell_on(self):
        self.make_server()
        status, _, _ = self.request_raw("GET", "/api/ping")
        self.assertEqual(status, 401)
        status, data = self.request("GET", "/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])

    def test_post_to_static_path_is_404(self):
        self.make_server()
        status, _, _ = self.request_raw("POST", "/index.html")
        self.assertEqual(status, 404)


class TestAvatarStaticShell(ServerFixture):
    """صور معرض الأفاتار: تُخدَم بلا رمز من مجلد القشرة المؤقت،
    وبالقائمة البيضاء الستّية فقط — غيرها 404 مهما وُجد على القرص."""

    DUMMY = b"\x89PNG-dummy-avatar-bytes"

    def make_avatar_server(self):
        pwa = Path(self.tmp.name) / "pwa_with_avatars"
        (pwa / "avatars").mkdir(parents=True)
        (pwa / "index.html").write_bytes(b"<html>shell</html>")
        (pwa / "avatars" / "bot_1.png").write_bytes(self.DUMMY)
        # ملف موجود على القرص لكنه خارج القائمة البيضاء الستّية.
        (pwa / "avatars" / "bot_99.png").write_bytes(b"not-whitelisted")
        return self.make_server(pwa_dir=pwa)

    def test_avatar_both_shapes_200_png(self):
        self.make_avatar_server()
        for path in ("/avatars/bot_1.png", "/app/avatars/bot_1.png"):
            status, headers, raw = self.request_raw("GET", path)
            self.assertEqual(status, 200, path)
            self.assertEqual(headers["content-type"], "image/png", path)
            self.assertEqual(raw, self.DUMMY, path)

    def test_non_gallery_avatar_names_are_404(self):
        self.make_avatar_server()
        for path in (
            "/avatars/bot_99.png",   # موجود على القرص لكن غير معرضي
            "/app/avatars/bot_99.png",
            "/avatars/app.js",       # اسم قشرة عادي تحت avatars/
            "/avatars/../app.js",    # عبور لا يطابق أي شكل مسموح
            "/app/avatars/../../krouchi_dz/server.py",
        ):
            status, _, _ = self.request_raw("GET", path)
            self.assertEqual(status, 404, path)


class TestPwaDirResolution(ServerFixture):
    """تحديد مجلد القشرة: متغيّر البيئة أولاً، والصريح عند البناء."""

    def test_env_var_wins(self):
        custom = Path(self.tmp.name) / "custom_pwa"
        custom.mkdir()
        (custom / "index.html").write_bytes(b"<html>custom</html>")
        old = os.environ.get("KROUCHI_PWA_DIR")
        os.environ["KROUCHI_PWA_DIR"] = str(custom)
        try:
            self.assertEqual(find_pwa_dir(), custom)
        finally:
            if old is None:
                del os.environ["KROUCHI_PWA_DIR"]
            else:
                os.environ["KROUCHI_PWA_DIR"] = old

    def test_explicit_dir_is_used(self):
        custom = Path(self.tmp.name) / "explicit_pwa"
        custom.mkdir()
        (custom / "index.html").write_bytes(b"<html>explicit</html>")
        server = self.make_server(pwa_dir=custom)
        self.assertEqual(server.pwa_dir, custom)
        status, _, raw = self.request_raw("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"<html>explicit</html>")


class TestMissingPwaDir(ServerFixture):
    """بلا مجلد قشرة: المسارات الثابتة 404 وواجهة /api/* تعمل كاملة."""

    def test_static_routes_are_404(self):
        server = self.make_server(
            pwa_dir=Path(self.tmp.name) / "no_such_pwa"
        )
        self.assertIsNone(server.pwa_dir)
        for path in ("/", "/index.html", "/app/app.js"):
            status, _, _ = self.request_raw("GET", path)
            self.assertEqual(status, 404, path)

    def test_api_keeps_working_without_shell(self):
        self.make_server(pwa_dir=Path(self.tmp.name) / "no_such_pwa")
        status, data = self.request("GET", "/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        status, _ = self.request("GET", "/api/ping", token=None)
        self.assertEqual(status, 401)


class TestControlErrorArmor(ServerFixture):
    """درع _route_control (3.4): استثناء منفّذ/قائمة تحكّم = 500 JSON
    بجسم خطأ، لا اتصال مقطوع — والخادم يبقى حياً لطلب تالٍ."""

    def test_failing_window_lister_is_500_json_and_server_survives(self):
        def boom():
            raise RuntimeError("تعذّر تعداد النوافذ")

        self.make_server(window_lister=boom)
        status, data = self.request("GET", "/api/windows")
        self.assertEqual(status, 500)
        self.assertEqual(data, {"error": "تعذّر تعداد النوافذ"})
        # طلب تالٍ على اتصال جديد يعمل كالمعتاد
        status, data = self.request("GET", "/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])

    def test_failing_process_lister_is_500_json(self):
        def boom():
            raise OSError("انفجرت القائمة")

        self.make_server(process_lister=boom)
        status, data = self.request("GET", "/api/processes")
        self.assertEqual(status, 500)
        self.assertEqual(data["error"], "انفجرت القائمة")


class TestSkillsApi(ServerFixture):
    """نقاط المهارات (الإصدار 3.6.0): قراءة الفهرس والسجلّ برمز
    الربط (401 بلا رمز)، والتعليم POST يمرّ بوسيط الموافقات باسم
    «تحكّم الهاتف» وبنوع save_skill — قبولاً فيُحفَظ بمصدر taught،
    ورفضاً فلا يُحفَظ ويعود 403 denied."""

    def seed_skill(self):
        return self.gateway.call(
            lambda e: e.db.save_skill(
                "محضر اجتماع", "صيغة المحاضر", "الترويسة أولاً",
                origin="installed",
            )
        )

    def test_skills_require_token(self):
        self.make_server()
        status, _ = self.request("GET", "/api/skills", token=None)
        self.assertEqual(status, 401)
        status, _ = self.request("GET", "/api/skills", token="invalid")
        self.assertEqual(status, 401)
        status, _ = self.request(
            "POST", "/api/skills",
            {"name": "س", "instructions": "ص"}, token=None,
        )
        self.assertEqual(status, 401)

    def test_skills_list_and_get(self):
        self.make_server()
        self.seed_skill()
        status, data = self.request("GET", "/api/skills")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["skills"]), 1)
        entry = data["skills"][0]
        self.assertEqual(entry["name"], "محضر اجتماع")
        self.assertEqual(entry["description"], "صيغة المحاضر")
        self.assertEqual(entry["origin"], "installed")
        self.assertNotIn("instructions", entry)  # الفهرس بلا تعليمات
        status, data = self.request(
            "GET", "/api/skills/" + urllib.parse.quote("محضر اجتماع")
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["skill"]["instructions"], "الترويسة أولاً")
        status, _ = self.request(
            "GET", "/api/skills/" + urllib.parse.quote("غائبة")
        )
        self.assertEqual(status, 404)

    def test_teach_skill_bad_body_is_400(self):
        self.make_server()
        status, _ = self.request("POST", "/api/skills", {"name": "س"})
        self.assertEqual(status, 400)
        status, _ = self.request(
            "POST", "/api/skills", {"name": "  ", "instructions": "ص"}
        )
        self.assertEqual(status, 400)

    def teach_in_thread(self, body):
        holder = {}

        def run():
            holder["result"] = self.request("POST", "/api/skills", body)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, holder

    def test_teach_skill_approved_saves_as_taught(self):
        self.make_server()
        thread, holder = self.teach_in_thread(
            {
                "name": "مهارة الهاتف",
                "description": "علّمها الهاتف",
                "instructions": "خطوات من الهاتف",
            }
        )
        item = self.wait_pending_http()
        self.assertEqual(item["tool"], "save_skill")
        self.assertEqual(item["bot_name"], "تحكّم الهاتف")
        self.assertIn("مهارة الهاتف", item["summary"])
        status, _ = self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "approve"}
        )
        self.assertEqual(status, 200)
        thread.join(10.0)
        status, payload = holder["result"]
        self.assertEqual(status, 200)
        self.assertEqual(payload["skill"]["origin"], "taught")
        skill = self.gateway.call(lambda e: e.db.get_skill("مهارة الهاتف"))
        self.assertEqual(skill["instructions"], "خطوات من الهاتف")

    def test_teach_skill_denied_is_403_and_not_saved(self):
        self.make_server()
        thread, holder = self.teach_in_thread(
            {"name": "مرفوضة", "instructions": "لا تُحفظ"}
        )
        item = self.wait_pending_http()
        self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "deny"}
        )
        thread.join(10.0)
        status, payload = holder["result"]
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "denied")
        skill = self.gateway.call(lambda e: e.db.get_skill("مرفوضة"))
        self.assertIsNone(skill)


class TestChatAttachmentsApi(ServerFixture):
    """POST /api/chat بمرفقات زرّ + (الإصدار 3.6.0): النصّية تصل
    النموذج بعنوانها، والصور أجزاء حقيقية، والشكل الفاسد 400."""

    def make_bot(self, mock):
        self.make_server(mock)
        return self.gateway.call(
            lambda e: e.create_bot("محادث", "openrouter")
        )

    def test_chat_with_text_attachment(self):
        mock = MockProvider([ChatResult(text="تم التلخيص")])
        bot_id = self.make_bot(mock)
        status, payload = self.request(
            "POST", "/api/chat",
            {
                "bot_id": bot_id,
                "text": "لخّص",
                "attachments": [
                    {
                        "kind": "text", "name": "وثيقة.txt",
                        "text": "محتوى الوثيقة المرفقة",
                    }
                ],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["reply"], "تم التلخيص")
        sent_user = mock.calls[0]["messages"][-1]
        self.assertIn("📎 ملف مرفق: وثيقة.txt", sent_user["content"])
        self.assertIn("محتوى الوثيقة المرفقة", sent_user["content"])

    def test_chat_with_image_attachment(self):
        mock = MockProvider([ChatResult(text="أرى الصورة")])
        bot_id = self.make_bot(mock)
        status, _ = self.request(
            "POST", "/api/chat",
            {
                "bot_id": bot_id,
                "text": "ما هذه؟",
                "attachments": [
                    {
                        "kind": "image", "name": "صورة.png",
                        "data_uri": "data:image/png;base64,QUJD",
                    }
                ],
            },
        )
        self.assertEqual(status, 200)
        sent_user = mock.calls[0]["messages"][-1]
        self.assertIsInstance(sent_user["content"], list)
        self.assertEqual(sent_user["content"][1]["type"], "image_url")

    def test_chat_with_bad_attachment_is_400(self):
        mock = MockProvider([ChatResult(text="ردّ")])
        bot_id = self.make_bot(mock)
        status, _ = self.request(
            "POST", "/api/chat",
            {
                "bot_id": bot_id,
                "text": "سلام",
                "attachments": [{"kind": "video", "name": "v.mp4"}],
            },
        )
        self.assertEqual(status, 400)
        status, _ = self.request(
            "POST", "/api/chat",
            {
                "bot_id": bot_id,
                "text": "سلام",
                "attachments": [
                    {"kind": "image", "name": "x", "data_uri": "http://x/y"}
                ],
            },
        )
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
