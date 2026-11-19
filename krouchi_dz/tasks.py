"""مهام البوتات الخلفية في Krouchi_DZ — تنفيذ طويل بلا حجب للواجهات.

المهمة: رسالة يوجّهها الهاتف إلى بوت على الحاسوب وتبقى تعمل في
الخلفية (دقائق إن لزم) بينما تبقى المحادثة والواجهة حرّتين. كل مهمة
تُنفَّذ بمحرّك ChatEngine مخصّص لها (اتصال SQLite خاص بها على نفس
ملف القاعدة) لكنها تشارك الجميع: ملف المزوّدين والأسرار نفسهما،
وسجلّ الموافقات المشترك نفسه — فطلبات أدوات المهمة بنمط ask تظهر في
/api/approvals وتُحسَم من الهاتف أو الحاسوب كطلبات المحادثة حرفياً،
وحالة المهمة تعكس الانتظار: waiting_approval ما دام لها طلب معلّق.

الحالات: queued → running ⇄ waiting_approval → done | failed | cancelled.
الإلغاء تعاوني: علم في الذاكرة يفحصه المحرّك بين الجولات (should_cancel)،
وإلغاء مهمة منتظرة يسحب طلباتها المعلّقة من السجلّ فيُرفَض الإجراء
الحالي وتنتهي المهمة ملغاة عند أول فحص. عند بدء الخادم، كل مهمة
بقيت بحالة نشطة من تشغيل سابق تُختم failed بخطأ "interrupted".

سلامة الخيوط: مخزن المهام اتصال SQLite خاص (check_same_thread=False)
تحرسه قفل واحد؛ خيوط العمال تنشئ محرّكاتها وتستعملها وتغلقها داخل
خيطها فقط.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .engine import ChatCancelled

TASK_STATUSES = (
    "queued", "running", "waiting_approval", "done", "failed", "cancelled",
)
FINAL_STATUSES = ("done", "failed", "cancelled")
ACTIVE_STATUSES = ("queued", "running", "waiting_approval")
MAX_LOG_EVENTS = 200          # حدّ أحداث سجلّ المهمة المحفوظة
MAX_TASKS_LISTED = 100        # حدّ قائمة المهام في GET /api/tasks
INTERRUPTED_ERROR = "interrupted"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


TASKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id      INTEGER NOT NULL REFERENCES bots(id),
    title       TEXT NOT NULL DEFAULT '',
    prompt      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'queued',
    result      TEXT,
    error       TEXT,
    log         TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
"""


class TaskStore:
    """عمليات جدول tasks باتصال خاص وقفل واحد — آمن من أي خيط."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(TASKS_SCHEMA)
        self.conn.commit()
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    # -- إنشاء وقراءة ------------------------------------------------------
    def create_task(self, bot_id: int, title: str, prompt: str) -> dict:
        with self._lock:
            cur = self.conn.execute(
                """
                INSERT INTO tasks (bot_id, title, prompt, status, log, created_at)
                VALUES (?, ?, ?, 'queued', '[]', ?)
                """,
                (bot_id, title, prompt, _now()),
            )
            self.conn.commit()
            return self._get_locked(int(cur.lastrowid))

    def _get_locked(self, task_id: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT t.*, b.name AS bot_name FROM tasks t
            LEFT JOIN bots b ON b.id = t.bot_id WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_task(self, task_id: int) -> dict | None:
        with self._lock:
            return self._get_locked(task_id)

    def list_tasks(self, limit: int = MAX_TASKS_LISTED) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT t.*, b.name AS bot_name FROM tasks t
                LEFT JOIN bots b ON b.id = t.bot_id
                ORDER BY t.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # -- تحديث الحالة والسجلّ ------------------------------------------------
    def update_task(self, task_id: int, **fields) -> None:
        """يحدّث حقولاً بعينها (status/result/error/started_at/finished_at)."""
        if not fields:
            return
        assignments = ", ".join(f"{col} = ?" for col in fields)
        with self._lock:
            self.conn.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?",
                (*fields.values(), task_id),
            )
            self.conn.commit()

    def set_status_if(
        self, task_id: int, expected: tuple[str, ...], new_status: str
    ) -> bool:
        """ينقل الحالة فقط إن كانت الحالية إحدى المتوقّعة (يمنع سباق الختام)."""
        placeholders = ", ".join("?" for _ in expected)
        with self._lock:
            cur = self.conn.execute(
                f"UPDATE tasks SET status = ? WHERE id = ? AND status IN ({placeholders})",
                (new_status, task_id, *expected),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def append_log(self, task_id: int, kind: str, text: str = "") -> None:
        """يضيف حدثاً لسجلّ المهمة (بحدّ أقصى MAX_LOG_EVENTS حدثاً)."""
        event = {"ts": _now(), "kind": kind, "text": text}
        with self._lock:
            row = self.conn.execute(
                "SELECT log FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return
            try:
                events = json.loads(row["log"] or "[]")
            except ValueError:
                events = []
            events.append(event)
            del events[:-MAX_LOG_EVENTS]
            self.conn.execute(
                "UPDATE tasks SET log = ? WHERE id = ?",
                (json.dumps(events, ensure_ascii=False), task_id),
            )
            self.conn.commit()

    def mark_interrupted(self) -> int:
        """يختم كل مهمة نشطة من تشغيل سابق: failed / interrupted."""
        with self._lock:
            cur = self.conn.execute(
                """
                UPDATE tasks SET status = 'failed', error = ?,
                       finished_at = ?
                WHERE status IN ('queued', 'running', 'waiting_approval')
                """,
                (INTERRUPTED_ERROR, _now()),
            )
            self.conn.commit()
            return cur.rowcount


class TaskManager:
    """مشغّل المهام: عمال خلفيون + مراقب لحالة انتظار الموافقة.

    engine_factory: دالة بلا معاملات تعيد ChatEngine جديداً مخصّصاً
    لمهمة واحدة (يُنشأ ويُستعمل ويُغلق داخل خيط العامل). registry:
    سجلّ الموافقات المشترك نفسه الذي يستعمله محرّك المحادثة.
    """

    def __init__(self, store: TaskStore, engine_factory, registry, workers: int = 2):
        self.store = store
        self.engine_factory = engine_factory
        self.registry = registry
        self.workers_count = max(1, int(workers))
        self._queue: list[int] = []
        self._queue_cond = threading.Condition()
        self._cancel_events: dict[int, threading.Event] = {}
        self._threads: list[threading.Thread] = []
        self._monitor: threading.Thread | None = None
        self._stopped = threading.Event()
        self._seen_pending: set[str] = set()
        self._seen_resolved: set[str] = set()
        self._events_lock = threading.Lock()

    # -- البدء والإيقاف ------------------------------------------------------
    def start(self) -> None:
        """يختم مهام التشغيل السابق المنقطعة ويشغّل العمال والمراقب."""
        self.store.mark_interrupted()
        for index in range(self.workers_count):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"krouchi-task-{index}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)
        self._monitor = threading.Thread(
            target=self._monitor_loop, name="krouchi-task-monitor", daemon=True
        )
        self._monitor.start()

    def stop(self) -> None:
        self._stopped.set()
        with self._queue_cond:
            self._queue_cond.notify_all()

    # -- واجهة الخادم ---------------------------------------------------------
    def submit(self, bot_id: int, title: str, prompt: str) -> dict:
        task = self.store.create_task(bot_id, title, prompt)
        self.store.append_log(task["id"], "queued", title)
        with self._queue_cond:
            self._queue.append(task["id"])
            self._queue_cond.notify()
        return task

    def cancel(self, task_id: int) -> str:
        """يطلب إلغاء مهمة: تعيد "ok" | "not_found" | "final".

        المعلّقة في الطابور تُختم فوراً؛ الجارية تُعلَّم بعلم الإلغاء
        وتُسحَب طلبات موافقتها المعلّقة (رفضاً) فينفكّ انتظارها،
        ويختمها عاملها cancelled عند أول فحص تعاوني.
        """
        task = self.store.get_task(task_id)
        if task is None:
            return "not_found"
        if task["status"] in FINAL_STATUSES:
            return "final"
        if task["status"] == "queued":
            if self.store.set_status_if(task_id, ("queued",), "cancelled"):
                self.store.update_task(task_id, finished_at=_now())
                self.store.append_log(task_id, "cancelled", "أُلغيت قبل أن تبدأ")
                return "ok"
            task = self.store.get_task(task_id)  # سبقنا عامل إليها
            if task is None or task["status"] in FINAL_STATUSES:
                return "final"
        event = self._cancel_events.setdefault(task_id, threading.Event())
        event.set()
        for item in self.registry.pending():
            if item.request.task_id == task_id:
                self.registry.expire(item.id)
        return "ok"

    # -- العمال ----------------------------------------------------------------
    def _worker_loop(self) -> None:
        while not self._stopped.is_set():
            with self._queue_cond:
                while not self._queue and not self._stopped.is_set():
                    self._queue_cond.wait(0.5)
                if self._stopped.is_set():
                    return
                if not self._queue:
                    continue
                task_id = self._queue.pop(0)
            self._run_task(task_id)

    def _run_task(self, task_id: int) -> None:
        if not self.store.set_status_if(task_id, ("queued",), "running"):
            return  # أُلغيت وهي في الطابور
        task = self.store.get_task(task_id)
        if task is None:
            return
        cancel_event = self._cancel_events.setdefault(task_id, threading.Event())
        self.store.update_task(task_id, started_at=_now())
        self.store.append_log(task_id, "started", task["title"])
        engine = None
        outcome: tuple[str, str | None] = ("done", None)
        try:
            engine = self.engine_factory()
            reply = engine.send_message(
                task["bot_id"],
                task["prompt"],
                should_cancel=cancel_event.is_set,
                on_event=lambda kind, text: self.store.append_log(
                    task_id, kind, text
                ),
                task_id=task_id,
            )
            outcome = ("cancelled", None) if cancel_event.is_set() else ("done", reply)
        except ChatCancelled:
            outcome = ("cancelled", None)
        except Exception as exc:  # فشل المهمة يُسجَّل ولا يقتل العامل
            outcome = ("failed", str(exc))
        # أحداث الموافقة تُزامَن حتمياً قبل نشر الحالة النهائية — فلا
        # يسبق ختمُ المهمة سجلَّها أبداً مهما قصُرت نافذة الانتظار.
        self._sync_approval_events()
        status, payload = outcome
        if status == "done":
            self.store.update_task(
                task_id, status="done", result=payload, finished_at=_now()
            )
            self.store.append_log(task_id, "finished", "")
        elif status == "cancelled":
            self.store.update_task(
                task_id, status="cancelled", finished_at=_now()
            )
            self.store.append_log(task_id, "cancelled", "أُلغيت أثناء التنفيذ")
        else:
            self.store.update_task(
                task_id, status="failed", error=payload, finished_at=_now()
            )
            self.store.append_log(task_id, "failed", payload or "")
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass
        self._cancel_events.pop(task_id, None)

    # -- مراقب الموافقات -------------------------------------------------------
    def _monitor_loop(self) -> None:
        """يعكس انتظار الموافقة على حالة المهام ويسجّل أحداثه في سجلّاتها."""
        while not self._stopped.wait(0.15):
            try:
                self._monitor_tick()
            except Exception:
                pass  # المراقب مساعد — خطؤه لا يُسقط شيئاً

    def _sync_approval_events(self) -> dict[int, list]:
        """يسجّل أحداث الموافقة الجديدة في سجلّات مهامها؛ يعيد المعلّق بمهامه.

        يُستدعى من المراقب دورياً ومن العامل قبل ختم مهمته — فالأحداث
        مضمونة الظهور في السجلّ ولو لم يلحق المراقب نافذة الانتظار.
        طلب حُسم قبل أن يُرى معلّقاً يُسجَّل طلبه ثم قراره معاً.
        """
        pending_by_task: dict[int, list] = {}
        with self._events_lock:
            for item in self.registry.pending():
                task_id = item.request.task_id
                if task_id is None:
                    continue
                pending_by_task.setdefault(task_id, []).append(item)
                if item.id not in self._seen_pending:
                    self._seen_pending.add(item.id)
                    self.store.append_log(
                        task_id, "approval_requested",
                        f"{item.request.action}: {item.id}",
                    )
            for item in self.registry.resolved_since(0.0):
                task_id = item.request.task_id
                if task_id is None or item.id in self._seen_resolved:
                    continue
                self._seen_resolved.add(item.id)
                if item.id not in self._seen_pending:
                    self._seen_pending.add(item.id)
                    self.store.append_log(
                        task_id, "approval_requested",
                        f"{item.request.action}: {item.id}",
                    )
                self.store.append_log(
                    task_id, "approval_decided",
                    f"{item.request.action}: "
                    f"{'approved' if item.decision else 'denied'} ({item.resolved_by})",
                )
        return pending_by_task

    def _monitor_tick(self) -> None:
        pending_by_task = self._sync_approval_events()
        active = [
            t for t in self.store.list_tasks(limit=MAX_TASKS_LISTED)
            if t["status"] in ("running", "waiting_approval")
        ]
        for task in active:
            if task["id"] in pending_by_task:
                self.store.set_status_if(
                    task["id"], ("running",), "waiting_approval"
                )
            else:
                self.store.set_status_if(
                    task["id"], ("waiting_approval",), "running"
                )
        # تنظيف ذاكرة المراقب من معرّفات لم تعد معلّقة ولا محسومة حديثاً
        if len(self._seen_pending) > 500:
            self._seen_pending = {
                i.id for i in self.registry.pending()
            } & self._seen_pending
        if len(self._seen_resolved) > 1000:
            self._seen_resolved = set(list(self._seen_resolved)[-200:])


def task_summary(task: dict) -> dict:
    """شكل المهمة في قوائم GET /api/tasks."""
    return {
        "id": task["id"],
        "bot_id": task["bot_id"],
        "bot_name": task.get("bot_name") or "",
        "title": task["title"],
        "status": task["status"],
        "created_at": task["created_at"],
        "started_at": task["started_at"],
        "finished_at": task["finished_at"],
    }


def task_detail(task: dict) -> dict:
    """شكل المهمة الكامل في GET /api/tasks/<id> (مع السجلّ محلّلاً)."""
    detail = task_summary(task)
    try:
        log = json.loads(task.get("log") or "[]")
    except ValueError:
        log = []
    detail.update(
        {
            "prompt": task["prompt"],
            "result": task["result"],
            "error": task["error"],
            "log": log,
        }
    )
    return detail
