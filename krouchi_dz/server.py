"""خادم مرافقة الهاتف في Krouchi_DZ — يربط تطبيق الهاتف بالحاسوب.

خادم HTTP محلي (المكتبة القياسية فقط، ThreadingHTTPServer) يُنصت على
0.0.0.0 بمنفذ 8765 افتراضياً، فيصل إليه تطبيق الهاتف على نفس الشبكة
المحلية ويستعمل بوتات الحاسوب نفسها: المحادثة تعمل هنا على محرّك
الحاسوب، بذاكرته وأدواته ووسيط موافقاته — الهاتف واجهة بعيدة فقط.

المصادقة: كل طلبات /api/* تحمل ترويسة X-Krouchi-Token مساوية لرمز
الربط (12+ حرفاً عشوائياً، يُولَّد مرة واحدة ويُحفَظ في إعدادات قاعدة
البيانات داخل مجلد البيانات، ويُجدَّد من نافذة «ربط الهاتف»).
المفقود أو الخاطئ = 401 JSON.

النقاط (JSON داخلاً وخارجاً):
- GET  /api/ping                 → {"ok", "app", "version"}
- GET  /api/bots                 → {"bots": [{"id","name","provider","model","mode"}]}
- GET  /api/history?bot=<id>     → {"messages": [...]} بنفس شكل المحرّك
- POST /api/chat {bot_id, text}  → {"reply": ...} (+ حقل approval أحياناً)
- GET  /api/approvals            → {"pending": [{"id","bot_name","tool","summary","created"}]}
- POST /api/approvals/<id> {"decision": "approve"|"deny"} → يحسم الطلب

دلالات الموافقة في /api/chat (قرار التصميم الموثّق):
المحادثة تعمل على الحاسوب عبر محرّكه؛ فإذا طلب بوت بنمط ask إجراءً
سُجّل الطلب في سجلّ الموافقات المعلّقة المشترك وبقيت المحادثة معلّقة
حتى يُحسَم الطلب — من بطاقة الحاسوب نفسها أو من الهاتف عبر
POST /api/approvals/<id> — أو تنتهي مهلة الوسيط (120 ثانية في الواجهة)
فيُرفَض تلقائياً (فشل مُغلق) وتُكمل المحادثة بردّها النهائي.
ردّ /api/chat يحمل "reply" دائماً عند النجاح؛ وإن حُسمت موافقات أثناء
هذه المحادثة أُضيف حقل "approval": ‏"denied" إن رُفض أو انتهت مهلة
طلب واحد على الأقل، وإلا "approved". وإن لم يُطلب أي إجراء أثناء
المحادثة لا يظهر الحقل إطلاقاً.

سلامة الخيوط: المحرّك مربوط بخيط مالكه (SQLite)، فلا يلمسه الخادم
مباشرة أبداً — كل وصول إليه يمرّ عبر engine_call التي يقدّمها المضيف
(في الواجهة: EngineRunner.call_blocking؛ برمجياً: EngineGateway هنا).
"""

from __future__ import annotations

import json
import queue
import secrets
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .broker import PendingApprovals, request_summary

DEFAULT_PORT = 8765
TOKEN_MIN_CHARS = 12
MAX_BODY_BYTES = 1_000_000  # حدّ حجم جسم الطلب — طلبات الربط صغيرة بطبيعتها

# مفاتيح الإعدادات في جدول settings داخل قاعدة بيانات مجلد البيانات.
SETTING_TOKEN = "companion_token"
SETTING_PORT = "companion_port"
SETTING_AUTOSTART = "companion_autostart"


# ======================================================================
# رمز الربط وعناوين الشبكة
# ======================================================================
def generate_token() -> str:
    """رمز ربط عشوائي جديد (16 حرفاً من token_urlsafe(12))."""
    return secrets.token_urlsafe(12)


def get_or_create_token(db) -> str:
    """يقرأ رمز الربط من الإعدادات؛ يولّده ويحفظه عند أول مرة فقط."""
    token = db.get_setting(SETTING_TOKEN, "")
    if not token:
        token = generate_token()
        db.set_setting(SETTING_TOKEN, token)
    return token


def regenerate_token(db) -> str:
    """يولّد رمز ربط جديداً ويحفظه (يُبطل الرمز القديم فوراً عند الخادم)."""
    token = generate_token()
    db.set_setting(SETTING_TOKEN, token)
    return token


def lan_ips() -> list[str]:
    """عناوين IPv4 المحلية للحاسوب على الشبكة (بلا عنوان الاسترجاع)."""
    ips: list[str] = []

    def _add(ip: str | None) -> None:
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.append(ip)

    try:  # العنوان الأساسي الذي تخرج منه الحزم فعلياً
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            _add(sock.getsockname()[0])
    except OSError:
        pass
    try:  # كل العناوين المرتبطة باسم المضيف (واجهات إضافية)
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            _add(info[4][0])
    except OSError:
        pass
    return ips


# ======================================================================
# بوّابة المحرّك: خيط واحد يملك المحرّك ويُسلسِل الوصول إليه
# ======================================================================
class EngineGateway:
    """تملك محرّكاً داخل خيطها وتُنفّذ المهام المرسلة إليه بالتتابع.

    الصورة البرمجية من EngineRunner في الواجهة (بلا Tk): للاستعمال
    الخادمي/الرأسي. call(fn) ترسل دالة تأخذ المحرّك وتنتظر نتيجتها
    حاجبةً الخيط المنادي — آمنة من أي خيط، ولا تلمس المحرّك إلا في
    خيط البوّابة حيث تعيش قاعدة SQLite.
    """

    def __init__(self, engine_factory):
        self._factory = engine_factory
        self.engine = None
        self._jobs: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._init_error: Exception | None = None
        self._thread = threading.Thread(
            target=self._loop, name="krouchi-gateway", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(30.0):
            raise TimeoutError("تأخّر إنشاء المحرّك في البوّابة")
        if self._init_error is not None:
            raise self._init_error

    def _loop(self) -> None:
        try:
            engine = self._factory()
        except Exception as exc:  # فشل الإنشاء يُبلَّغ ولا يموت الخيط صامتاً
            self._init_error = exc
            self._ready.set()
            return
        self.engine = engine
        self._ready.set()
        while True:
            job = self._jobs.get()
            if job is None:
                try:
                    engine.close()
                except Exception:
                    pass
                return
            fn, holder, event = job
            try:
                holder["value"] = fn(engine)
                holder["ok"] = True
            except Exception as exc:
                holder["value"] = exc
                holder["ok"] = False
            event.set()

    def call(self, fn, timeout: float | None = None):
        """ينفّذ fn(engine) على خيط البوّابة وينتظر نتيجتها (تحجب المنادي)."""
        holder: dict = {}
        event = threading.Event()
        self._jobs.put((fn, holder, event))
        if not event.wait(timeout):
            raise TimeoutError("انتهت مهلة مهمة المحرّك")
        if holder["ok"]:
            return holder["value"]
        raise holder["value"]

    def close(self) -> None:
        self._jobs.put(None)


# ======================================================================
# خادم المرافقة
# ======================================================================
def _approval_summary(item) -> dict:
    """شكل طلب معلّق واحد كما يخرج في GET /api/approvals."""
    request = item.request
    return {
        "id": item.id,
        "bot_name": request.bot_name,
        "tool": request.action,
        "summary": request_summary(request),
        "created": item.created_at,
    }


class CompanionServer:
    """خادم HTTP للهاتف المرافق: بدء/إيقاف برمجي، ورمز ربط قابل للتبديل.

    engine_call: دالة (fn) -> نتيجة، تُنفّذ fn(engine) على خيط مالك
    المحرّك حاجبةً (انظر ترويسة الوحدة). registry: سجلّ الموافقات
    المعلّقة المشترك نفسه الذي يغذّي وسيط المحرّك وبطاقة الواجهة.
    """

    def __init__(
        self,
        engine_call,
        registry: PendingApprovals,
        token: str,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
    ):
        if len(token or "") < TOKEN_MIN_CHARS:
            raise ValueError("رمز الربط قصير — 12 حرفاً على الأقل")
        self.engine_call = engine_call
        self.registry = registry
        self.host = host
        self._port = int(port)
        self._token = token
        self._token_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- الحالة ---------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._httpd is not None

    @property
    def port(self) -> int:
        """المنفذ الفعلي (بعد الربط إن كان المطلوب 0 = أي منفذ حرّ)."""
        if self._httpd is not None:
            return int(self._httpd.server_address[1])
        return self._port

    @property
    def token(self) -> str:
        with self._token_lock:
            return self._token

    def set_token(self, token: str) -> None:
        """يبدّل رمز الربط الساري فوراً (بعد تجديده في الإعدادات)."""
        if len(token or "") < TOKEN_MIN_CHARS:
            raise ValueError("رمز الربط قصير — 12 حرفاً على الأقل")
        with self._token_lock:
            self._token = token

    def check_token(self, presented: str | None) -> bool:
        if not presented:
            return False
        return secrets.compare_digest(presented, self.token)

    # -- البدء والإيقاف ----------------------------------------------------
    def start(self) -> None:
        """يربط المنفذ ويخدم في خيط خاص. لا شيء إن كان يعمل أصلاً."""
        with self._state_lock:
            if self._httpd is not None:
                return
            httpd = ThreadingHTTPServer((self.host, self._port), _Handler)
            httpd.daemon_threads = True
            httpd.companion = self  # type: ignore[attr-defined]
            self._httpd = httpd
            self._thread = threading.Thread(
                target=httpd.serve_forever,
                name="krouchi-companion",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """يوقف الخدمة ويحرّر المنفذ. لا شيء إن كان متوقّفاً أصلاً."""
        with self._state_lock:
            httpd, self._httpd = self._httpd, None
            self._thread = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()

    # -- عمليات المحرّك (تُستدعى من معالج الطلبات) ---------------------------
    def list_bots(self) -> list[dict]:
        def job(engine):
            bots = []
            for bot in engine.db.list_bots():
                cfg = engine.providers.get(bot["provider_name"])
                bots.append(
                    {
                        "id": bot["id"],
                        "name": bot["name"],
                        "provider": bot["provider_name"],
                        "model": bot["model"]
                        or (cfg.default_model if cfg else ""),
                        "mode": bot["approval_mode"],
                    }
                )
            return bots

        return self.engine_call(job)

    def history(self, bot_id: int) -> list[dict] | None:
        """رسائل بوت بنفس شكل تخزين المحرّك؛ None إن لم يوجد البوت."""

        def job(engine):
            if engine.db.get_bot(bot_id) is None:
                return None
            return engine.history(bot_id)

        return self.engine_call(job)

    def chat(self, bot_id: int, text: str) -> dict | None:
        """محادثة كاملة على الحاسوب؛ None إن لم يوجد البوت.

        انظر دلالات حقل "approval" في ترويسة الوحدة.
        """

        def job(engine):
            if engine.db.get_bot(bot_id) is None:
                return None
            return engine.send_message(bot_id, text)

        started = time.monotonic()
        reply = self.engine_call(job)
        if reply is None:
            return None
        payload: dict = {"reply": reply}
        resolved = self.registry.resolved_since(started, bot_id=bot_id)
        if resolved:
            payload["approval"] = (
                "denied"
                if any(not item.decision for item in resolved)
                else "approved"
            )
        return payload


# ======================================================================
# معالج الطلبات
# ======================================================================
class _Handler(BaseHTTPRequestHandler):
    """يوجّه طلبات /api/* إلى الخادم المرافق بعد فحص رمز الربط."""

    server_version = "Krouchi_DZ"

    @property
    def _srv(self) -> CompanionServer:
        return self.server.companion  # type: ignore[attr-defined]

    def log_message(self, format, *args):  # صمت: لا سجلّ طلبات على الطرفية
        pass

    # -- أدوات الردّ والقراءة ----------------------------------------------
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("جسم الطلب أكبر من الحدّ")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("جسم الطلب ليس كائن JSON")
        return data

    # -- التوجيه --------------------------------------------------------------
    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        try:
            self._route(method)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # طلب واحد فاسد لا يُسقط الخادم
            try:
                self._send_json(500, {"error": f"خطأ داخلي: {exc}"})
            except Exception:
                pass

    def _route(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if not path.startswith("/api/"):
            return self._send_json(404, {"error": "مسار غير معروف"})
        if not self._srv.check_token(self.headers.get("X-Krouchi-Token")):
            return self._send_json(
                401, {"error": "رمز الربط مفقود أو غير صحيح"}
            )
        srv = self._srv

        if method == "GET" and path == "/api/ping":
            from . import __version__  # متأخراً عمداً: يفكّ أي دورة استيراد

            return self._send_json(
                200, {"ok": True, "app": "Krouchi_DZ", "version": __version__}
            )

        if method == "GET" and path == "/api/bots":
            return self._send_json(200, {"bots": srv.list_bots()})

        if method == "GET" and path == "/api/history":
            query = urllib.parse.parse_qs(parsed.query)
            raw_bot = (query.get("bot") or [""])[0]
            try:
                bot_id = int(raw_bot)
            except ValueError:
                return self._send_json(
                    400, {"error": "معامل bot مطلوب ويجب أن يكون رقماً"}
                )
            messages = srv.history(bot_id)
            if messages is None:
                return self._send_json(404, {"error": "بوت غير موجود"})
            return self._send_json(200, {"messages": messages})

        if method == "GET" and path == "/api/approvals":
            pending = [_approval_summary(i) for i in srv.registry.pending()]
            return self._send_json(200, {"pending": pending})

        if method == "POST" and path == "/api/chat":
            try:
                body = self._read_json_body()
            except ValueError as exc:
                return self._send_json(400, {"error": f"جسم غير صالح: {exc}"})
            bot_id = body.get("bot_id")
            text = body.get("text")
            if (
                not isinstance(bot_id, int)
                or isinstance(bot_id, bool)
                or not isinstance(text, str)
                or not text.strip()
            ):
                return self._send_json(
                    400,
                    {"error": "الحقول المطلوبة: bot_id (رقم) و text (نص)"},
                )
            try:
                payload = srv.chat(bot_id, text)
            except Exception as exc:  # فشل مزوّد/نموذج يُبلَّغ ولا يمرّ صامتاً
                return self._send_json(502, {"error": f"فشلت المحادثة: {exc}"})
            if payload is None:
                return self._send_json(404, {"error": "بوت غير موجود"})
            return self._send_json(200, payload)

        if method == "POST" and path.startswith("/api/approvals/"):
            item_id = path[len("/api/approvals/"):]
            if not item_id or "/" in item_id:
                return self._send_json(404, {"error": "مسار غير معروف"})
            try:
                body = self._read_json_body()
            except ValueError as exc:
                return self._send_json(400, {"error": f"جسم غير صالح: {exc}"})
            decision = body.get("decision")
            if decision not in ("approve", "deny"):
                return self._send_json(
                    400, {"error": "decision يجب أن تكون approve أو deny"}
                )
            approved = decision == "approve"
            if srv.registry.resolve(item_id, approved, source="phone"):
                return self._send_json(
                    200,
                    {
                        "ok": True,
                        "id": item_id,
                        "decision": "approved" if approved else "denied",
                    },
                )
            return self._send_json(
                404, {"error": "طلب غير موجود أو حُسم سابقاً"}
            )

        return self._send_json(404, {"error": "مسار غير معروف"})
