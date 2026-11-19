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
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import krouchi_dz
from krouchi_dz.broker import PendingApprovals
from krouchi_dz.engine import ChatEngine
from krouchi_dz.providers import ChatResult, MockProvider, ToolCall
from krouchi_dz.server import (
    CompanionServer,
    EngineGateway,
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

    def make_server(self, mock=None, ask_timeout=10.0):
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
        self.server = CompanionServer(
            engine_call=self.gateway.call,
            registry=self.registry,
            token=TOKEN,
            port=0,
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
        self.assertEqual(bot["provider"], "openrouter")
        self.assertEqual(bot["model"], "m-1")
        self.assertEqual(bot["mode"], "ask")

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


if __name__ == "__main__":
    unittest.main()
