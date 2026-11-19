"""اختبارات وسيط الموافقات: الأنماط الثلاثة ومسارات الفشل المُغلق والتدقيق."""

import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from krouchi_dz.broker import (
    ApprovalBroker,
    ApprovalRequest,
    PendingApprovals,
    request_summary,
)


def make_bot(mode):
    return {"id": 1, "name": "بوت اختبار", "approval_mode": mode}


class AuditSink:
    def __init__(self):
        self.rows = []

    def __call__(self, bot_id, action, decision, reason, details):
        self.rows.append(
            {"bot_id": bot_id, "action": action,
             "decision": decision, "reason": reason}
        )


class TestAskMode(unittest.TestCase):
    def test_approved(self):
        broker = ApprovalBroker(ask_callback=lambda req: True)
        d = broker.authorize(make_bot("ask"), "write_file", {"path": "x"})
        self.assertTrue(d.allowed)

    def test_denied_by_user(self):
        broker = ApprovalBroker(ask_callback=lambda req: False)
        d = broker.authorize(make_bot("ask"), "write_file", {"path": "x"})
        self.assertFalse(d.allowed)

    def test_no_callback_fails_closed(self):
        broker = ApprovalBroker(ask_callback=None)
        d = broker.authorize(make_bot("ask"), "run_command", {"command": "ls"})
        self.assertFalse(d.allowed)
        self.assertIn("رفض تلقائي", d.reason)

    def test_timeout_fails_closed(self):
        def slow(req):
            time.sleep(2.0)
            return True

        broker = ApprovalBroker(ask_callback=slow, ask_timeout=0.2)
        start = time.monotonic()
        d = broker.authorize(make_bot("ask"), "write_file", {"path": "x"})
        elapsed = time.monotonic() - start
        self.assertFalse(d.allowed)
        self.assertLess(elapsed, 1.5)

    def test_callback_exception_fails_closed(self):
        def boom(req):
            raise RuntimeError("عطل")

        broker = ApprovalBroker(ask_callback=boom)
        d = broker.authorize(make_bot("ask"), "read_file", {"path": "x"})
        self.assertFalse(d.allowed)

    def test_callback_receives_request_details(self):
        seen = {}

        def cb(req):
            seen.update(action=req.action, bot=req.bot_name,
                        path=req.params.get("path"))
            return True

        broker = ApprovalBroker(ask_callback=cb)
        broker.authorize(make_bot("ask"), "read_file", {"path": "doc.txt"})
        self.assertEqual(seen["action"], "read_file")
        self.assertEqual(seen["path"], "doc.txt")


class TestFullAndReadonly(unittest.TestCase):
    def test_full_allows_everything_without_callback(self):
        broker = ApprovalBroker(ask_callback=None)
        for action in ("read_file", "write_file", "run_command"):
            d = broker.authorize(make_bot("full"), action, {})
            self.assertTrue(d.allowed, action)

    def test_readonly_allows_read_only(self):
        broker = ApprovalBroker(ask_callback=lambda req: True)
        self.assertTrue(
            broker.authorize(make_bot("readonly"), "read_file", {}).allowed
        )
        self.assertFalse(
            broker.authorize(make_bot("readonly"), "write_file", {}).allowed
        )
        self.assertFalse(
            broker.authorize(make_bot("readonly"), "run_command", {}).allowed
        )

    def test_unknown_action_always_denied(self):
        broker = ApprovalBroker(ask_callback=lambda req: True)
        d = broker.authorize(make_bot("full"), "delete_everything", {})
        self.assertFalse(d.allowed)


class TestAudit(unittest.TestCase):
    def test_every_decision_logged(self):
        sink = AuditSink()
        broker = ApprovalBroker(ask_callback=lambda req: False, audit=sink)
        broker.authorize(make_bot("ask"), "write_file", {"path": "a"})
        broker.authorize(make_bot("readonly"), "read_file", {"path": "a"})
        self.assertEqual(len(sink.rows), 2)
        self.assertEqual(sink.rows[0]["decision"], "denied")
        self.assertEqual(sink.rows[1]["decision"], "allowed")
        self.assertTrue(all(r["reason"] for r in sink.rows))


class TestRegistryPath(unittest.TestCase):
    """مسار السجلّ المشترك: أي واجهة تحسم، والمهلة ترفض وتسحب الطلب."""

    def authorize_in_thread(self, broker, mode="ask", action="write_file"):
        holder = {}

        def run():
            holder["decision"] = broker.authorize(
                make_bot(mode), action, {"path": "x.txt", "content": "y"}
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, holder

    def wait_pending(self, registry, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pending = registry.pending()
            if pending:
                return pending[0]
            time.sleep(0.01)
        self.fail("لم يظهر أي طلب معلّق في السجلّ")

    def test_registry_approve_allows(self):
        registry = PendingApprovals()
        broker = ApprovalBroker(registry=registry, ask_timeout=10.0)
        thread, holder = self.authorize_in_thread(broker)
        item = self.wait_pending(registry)
        self.assertEqual(item.request.bot_name, "بوت اختبار")
        self.assertEqual(item.request.action, "write_file")
        self.assertTrue(registry.resolve(item.id, True, source="phone"))
        thread.join(3.0)
        self.assertTrue(holder["decision"].allowed)
        self.assertEqual(registry.pending(), [])

    def test_registry_deny_refuses(self):
        registry = PendingApprovals()
        broker = ApprovalBroker(registry=registry, ask_timeout=10.0)
        thread, holder = self.authorize_in_thread(broker)
        item = self.wait_pending(registry)
        self.assertTrue(registry.resolve(item.id, False, source="gui"))
        thread.join(3.0)
        self.assertFalse(holder["decision"].allowed)
        self.assertIn("رفض المستخدم", holder["decision"].reason)

    def test_registry_timeout_fails_closed_and_expires(self):
        registry = PendingApprovals()
        broker = ApprovalBroker(registry=registry, ask_timeout=0.2)
        start = time.monotonic()
        d = broker.authorize(make_bot("ask"), "write_file", {"path": "x"})
        elapsed = time.monotonic() - start
        self.assertFalse(d.allowed)
        self.assertIn("انتهت مهلة", d.reason)
        self.assertLess(elapsed, 1.5)
        # الطلب سُحب من المعلّق وسُجّل محسوماً بالمهلة
        self.assertEqual(registry.pending(), [])
        resolved = registry.resolved_since(0.0)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].resolved_by, "timeout")
        self.assertFalse(resolved[0].decision)

    def test_resolve_unknown_or_twice_fails(self):
        registry = PendingApprovals()
        self.assertFalse(registry.resolve("nope", True))
        broker = ApprovalBroker(registry=registry, ask_timeout=10.0)
        thread, holder = self.authorize_in_thread(broker)
        item = self.wait_pending(registry)
        self.assertTrue(registry.resolve(item.id, True))
        self.assertFalse(registry.resolve(item.id, False))  # حُسم وانتهى
        thread.join(3.0)
        self.assertTrue(holder["decision"].allowed)

    def test_registry_path_audits_like_callback_path(self):
        registry = PendingApprovals()
        sink = AuditSink()
        broker = ApprovalBroker(registry=registry, ask_timeout=10.0, audit=sink)
        thread, holder = self.authorize_in_thread(broker)
        item = self.wait_pending(registry)
        registry.resolve(item.id, True, source="phone")
        thread.join(3.0)
        self.assertEqual(len(sink.rows), 1)
        self.assertEqual(sink.rows[0]["decision"], "allowed")


class TestRequestSummary(unittest.TestCase):
    """نصّ الهدف المشترك بين بطاقة الواجهة وملخّصات خادم الهاتف."""

    def make_request(self, action, params):
        return ApprovalRequest(
            bot_id=1, bot_name="بوت", action=action, params=params, mode="ask"
        )

    def test_write_file_shows_path_and_content(self):
        text = request_summary(
            self.make_request(
                "write_file", {"path": "/tmp/a.txt", "content": "محتوى"}
            )
        )
        self.assertIn("/tmp/a.txt", text)
        self.assertIn("محتوى", text)

    def test_read_file_shows_path_only(self):
        text = request_summary(
            self.make_request("read_file", {"path": "/tmp/a.txt"})
        )
        self.assertEqual(text, "/tmp/a.txt")

    def test_run_command_verbatim(self):
        text = request_summary(
            self.make_request("run_command", {"command": "echo krouchi"})
        )
        self.assertEqual(text, "echo krouchi")


if __name__ == "__main__":
    unittest.main()
