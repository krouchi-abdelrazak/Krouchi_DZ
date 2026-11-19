"""اختبارات مهام البوتات الخلفية (الإصدار 3.2): دورة الحياة كاملة عبر
HTTP — إنشاء (بمعرّف نصّي أيضاً) ← تشغيل بمحرّك مخصّص ← نتيجة،
وانتظار الموافقة معكوساً على الحالة، وإلغاء المعلّقة والجارية،
وختم مهام التشغيل السابق المنقطعة عند بدء الخادم.
"""

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_server import ServerFixture  # noqa: E402

from krouchi_dz.engine import ChatEngine  # noqa: E402
from krouchi_dz.providers import ChatResult, MockProvider, ToolCall  # noqa: E402


class TaskFixture(ServerFixture):
    """خادم بمصنع مهام يبني محرّكاً لكل مهمة بمزوّد وهمي مكتوب."""

    def make_task_server(self, scripts=(), **kwargs):
        self._scripts = [list(s) for s in scripts]
        data_dir = Path(self.tmp.name) / "data"
        fixture = self

        def factory():
            script = fixture._scripts.pop(0) if fixture._scripts else []
            mock = MockProvider(script)
            return ChatEngine(
                data_dir,
                approval_registry=fixture.registry,
                ask_timeout=10.0,
                provider_factory=lambda cfg, key: mock,
            )

        kwargs.setdefault("task_engine_factory", factory)
        return self.make_server(**kwargs)

    def create_bot(self, name="منفّذ", mode="ask"):
        return self.gateway.call(
            lambda e: e.create_bot(name, "openrouter", approval_mode=mode)
        )

    def wait_task(self, task_id, statuses, timeout=12.0):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            status, data = self.request("GET", f"/api/tasks/{task_id}")
            self.assertEqual(status, 200)
            last = data["task"]
            if last["status"] in statuses:
                return last
            time.sleep(0.05)
        self.fail(f"المهمة {task_id} لم تصل إلى {statuses} — آخر حالة: {last}")


class TestTaskLifecycle(TaskFixture):
    def test_create_run_done_and_listed(self):
        self.make_task_server(scripts=[[ChatResult(text="نتيجة المهمة")]])
        bot_id = self.create_bot()
        # المعرّف كنصّ رقمي يُقبَل (نفس تسامح v3.1.1)
        status, data = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": str(bot_id), "title": "تلخيص", "prompt": "لخّص هذا"},
        )
        self.assertEqual(status, 201)
        task = data["task"]
        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["bot_id"], bot_id)
        self.assertEqual(task["title"], "تلخيص")
        self.assertTrue(task["created_at"])

        done = self.wait_task(task["id"], ("done",))
        self.assertEqual(done["result"], "نتيجة المهمة")
        self.assertIsNone(done["error"])
        self.assertEqual(done["bot_name"], "منفّذ")
        self.assertEqual(done["prompt"], "لخّص هذا")
        self.assertTrue(done["started_at"])
        self.assertTrue(done["finished_at"])
        kinds = [e["kind"] for e in done["log"]]
        self.assertIn("started", kinds)
        self.assertIn("finished", kinds)

        # تبقى في القائمة بعد اكتمالها، بأحدثها أولاً
        status, data = self.request("GET", "/api/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["tasks"]), 1)
        listed = data["tasks"][0]
        self.assertEqual(listed["id"], task["id"])
        self.assertEqual(listed["bot_name"], "منفّذ")
        self.assertEqual(listed["status"], "done")
        self.assertNotIn("prompt", listed)  # القائمة مختصرة بلا تفاصيل

    def test_create_unknown_bot_is_404(self):
        self.make_task_server()
        status, _ = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": 4242, "title": "س", "prompt": "ص"},
        )
        self.assertEqual(status, 404)

    def test_create_bad_body_is_400(self):
        self.make_task_server()
        bot_id = self.create_bot()
        status, _ = self.request(
            "POST", "/api/tasks", {"bot_id": bot_id, "title": "", "prompt": "ص"}
        )
        self.assertEqual(status, 400)

    def test_unknown_task_is_404(self):
        self.make_task_server()
        status, _ = self.request("GET", "/api/tasks/987")
        self.assertEqual(status, 404)
        status, _ = self.request("POST", "/api/tasks/987/cancel")
        self.assertEqual(status, 404)

    def test_cancel_finished_task_is_409(self):
        self.make_task_server(scripts=[[ChatResult(text="تم")]])
        bot_id = self.create_bot()
        _, data = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": bot_id, "title": "س", "prompt": "ص"},
        )
        task_id = data["task"]["id"]
        self.wait_task(task_id, ("done",))
        status, _ = self.request("POST", f"/api/tasks/{task_id}/cancel")
        self.assertEqual(status, 409)

    def test_failed_task_records_error(self):
        def bad_factory_engine(cfg, key):
            raise RuntimeError("مزوّد معطّل")

        data_dir = Path(self.tmp.name) / "data"
        fixture = self

        def factory():
            return ChatEngine(
                data_dir,
                approval_registry=fixture.registry,
                provider_factory=bad_factory_engine,
            )

        self.make_server(task_engine_factory=factory)
        bot_id = self.create_bot()
        _, data = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": bot_id, "title": "س", "prompt": "ص"},
        )
        failed = self.wait_task(data["task"]["id"], ("failed",))
        self.assertIn("مزوّد معطّل", failed["error"])


class TestTaskApprovalsAndCancel(TaskFixture):
    """مهمة بنمط ask تنتظر موافقة: حالتها waiting_approval، وإلغاؤها
    يسحب الطلب المعلّق فتنتهي ملغاة دون تنفيذ."""

    def tool_script(self, target: Path):
        return [
            ChatResult(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments={"path": str(target), "content": "محتوى"},
                    )
                ]
            ),
            ChatResult(text="انتهت المهمة"),
        ]

    def test_waiting_approval_then_cancel(self):
        target = Path(self.tmp.name) / "task_out.txt"
        self.make_task_server(scripts=[self.tool_script(target)])
        bot_id = self.create_bot()
        _, data = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": bot_id, "title": "كتابة", "prompt": "اكتب الملف"},
        )
        task_id = data["task"]["id"]

        item = self.wait_pending_http()
        self.assertEqual(item["task_id"], task_id)
        self.assertEqual(item["tool"], "write_file")
        waiting = self.wait_task(task_id, ("waiting_approval",))
        self.assertEqual(waiting["status"], "waiting_approval")

        status, data = self.request("POST", f"/api/tasks/{task_id}/cancel")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        cancelled = self.wait_task(task_id, ("cancelled",))
        kinds = [e["kind"] for e in cancelled["log"]]
        self.assertIn("approval_requested", kinds)
        self.assertIn("cancelled", kinds)
        self.assertFalse(target.exists())  # سُحب الطلب فلم يُكتب شيء

    def test_approved_task_tool_runs_and_finishes(self):
        target = Path(self.tmp.name) / "task_ok.txt"
        self.make_task_server(scripts=[self.tool_script(target)])
        bot_id = self.create_bot()
        _, data = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": bot_id, "title": "كتابة", "prompt": "اكتب الملف"},
        )
        task_id = data["task"]["id"]
        item = self.wait_pending_http()
        self.assertEqual(item["task_id"], task_id)
        status, _ = self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "approve"}
        )
        self.assertEqual(status, 200)
        done = self.wait_task(task_id, ("done",))
        self.assertEqual(done["result"], "انتهت المهمة")
        self.assertEqual(target.read_text(encoding="utf-8"), "محتوى")
        kinds = [e["kind"] for e in done["log"]]
        self.assertIn("approval_requested", kinds)
        self.assertIn("approval_decided", kinds)
        self.assertIn("tool", kinds)

    def test_cancel_queued_task(self):
        # عامل واحد مشغول بمهمة منتظرة موافقة ⇒ الثانية تبقى في الطابور
        target = Path(self.tmp.name) / "first.txt"
        self.make_task_server(
            scripts=[self.tool_script(target), [ChatResult(text="ثانية")]],
            task_workers=1,
        )
        bot_id = self.create_bot()
        _, first = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": bot_id, "title": "أولى", "prompt": "اكتب"},
        )
        first_id = first["task"]["id"]
        item = self.wait_pending_http()
        self.assertEqual(item["task_id"], first_id)
        _, second = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": bot_id, "title": "ثانية", "prompt": "انتظر"},
        )
        second_id = second["task"]["id"]
        _, data = self.request("GET", f"/api/tasks/{second_id}")
        self.assertEqual(data["task"]["status"], "queued")

        status, _ = self.request("POST", f"/api/tasks/{second_id}/cancel")
        self.assertEqual(status, 200)
        cancelled = self.wait_task(second_id, ("cancelled",))
        self.assertIsNone(cancelled["started_at"])

        # تنظيف: ارفض طلب الأولى فتنتهي مهمتها
        self.request(
            "POST", f"/api/approvals/{item['id']}", {"decision": "deny"}
        )
        self.wait_task(first_id, ("done", "failed"))


class TestInterruptedOnStart(TaskFixture):
    def test_stale_active_task_marked_failed_interrupted(self):
        self.make_task_server()
        bot_id = self.create_bot()
        _, data = self.request(
            "POST",
            "/api/tasks",
            {"bot_id": bot_id, "title": "عالقة", "prompt": "ص"},
        )
        task_id = data["task"]["id"]
        self.wait_task(task_id, ("done",))
        # زيّف حالة «كانت جارية عند انقطاع التشغيل السابق»
        self.server.task_store.update_task(
            task_id, status="running", finished_at=None
        )
        # أعد تشغيل الخادم على نفس القاعدة: البدء يختمها interrupted
        self.server.stop()
        self.gateway.close()
        self.make_task_server()
        status, data = self.request("GET", f"/api/tasks/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(data["task"]["status"], "failed")
        self.assertEqual(data["task"]["error"], "interrupted")


if __name__ == "__main__":
    unittest.main()
