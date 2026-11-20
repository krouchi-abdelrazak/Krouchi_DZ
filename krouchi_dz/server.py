"""خادم مرافقة الهاتف في Krouchi_DZ — يربط تطبيق الهاتف بالحاسوب.

خادم HTTP محلي (المكتبة القياسية فقط، ThreadingHTTPServer) يُنصت على
0.0.0.0 بمنفذ 8765 افتراضياً، فيصل إليه تطبيق الهاتف على نفس الشبكة
المحلية ويستعمل بوتات الحاسوب نفسها: المحادثة تعمل هنا على محرّك
الحاسوب، بذاكرته وأدواته ووسيط موافقاته — الهاتف واجهة بعيدة فقط.

المصادقة: كل طلبات /api/* تحمل ترويسة X-Krouchi-Token مساوية لرمز
الربط (12+ حرفاً عشوائياً، يُولَّد مرة واحدة ويُحفَظ في إعدادات قاعدة
البيانات داخل مجلد البيانات، ويُجدَّد من نافذة «ربط الهاتف»).
المفقود أو الخاطئ = 401 JSON.

قشرة تطبيق الويب (PWA): يخدم الخادم أيضاً ملفات مجلد «pwa» الثابتة
بلا رمز (القشرة عامة كملف APK نفسه؛ الحماية على /api/* فقط)، فيفتح
متصفح الهاتف http://<عنوان الحاسوب>:8765/ على التطبيق مباشرة،
وتعمل محادثة «الحاسوب» فيه بنفس الأصل فلا حاجب محتوى مختلطاً:
- GET /            → index.html
- GET /<file>      → ملف من القائمة البيضاء PWA_FILES
- GET /app/<file>  → الشكل الثاني لنفس الملفات
أي مسار آخر = 404، والخدمة بقائمة بيضاء بأسماء الأساس فقط فلا عبور
للمسارات. مكان المجلد يُحدَّد بـ find_pwa_dir()؛ وغيابه لا يعطّل
واجهة /api/* إطلاقاً — تُعطَّل القشرة وحدها مع ملاحظة عند بدء الخادم.

النقاط (JSON داخلاً وخارجاً):
- GET  /api/ping                 → {"ok", "app", "version"}
- GET  /api/bots                 → {"bots": [{"id","name","provider","model","mode","avatar"}]}
- GET  /api/history?bot=<id>     → {"messages": [...]} بنفس شكل المحرّك
- POST /api/chat {bot_id, text}  → {"reply": ...} (+ حقل approval أحياناً)
- GET  /api/approvals            → {"pending": [{"id","bot_name","tool","summary","created"}]}
- POST /api/approvals/<id> {"decision": "approve"|"deny"} → يحسم الطلب

الإصدار 3.2 — التحكّم الكلي ومهام البوتات:
- GET  /api/status               → حالة الحاسوب (نظام/قرص/ذاكرة/مدة تشغيل)
- عائلة التحكّم (تُعطَّل كلها بإعداد control_enabled=false ← 403):
  GET /api/files?path= · GET /api/file?path= · POST /api/run {command} ·
  POST /api/open {target} · GET /api/screenshot · POST /api/power {action} ·
  GET /api/printers · POST /api/print {path, printer?} ·
  POST /api/upload {path, content_b64} · GET/POST /api/clipboard
  أفعالها الكتابية تمرّ بوسيط الموافقات المشترك نفسه (باسم «تحكّم
  الهاتف»)، والطاقة بقوة سؤال دائماً (force_ask) ولو بلا بوت.
- المهام (لا يمسّها control_enabled):
  POST /api/tasks {bot_id, title, prompt} → 201 ·
  GET /api/tasks · GET /api/tasks/<id> · POST /api/tasks/<id>/cancel
  تُنفَّذ بمحرّكات مخصّصة في الخلفية (tasks.py) وتشارك سجلّ الموافقات.

الإصدار 3.3 — الشاشة الحية والإدخال عن بُعد (من عائلة التحكّم أيضاً):
- GET  /api/screen/stream?w=&q=&fps= → بثّ سطح المكتب MJPEG
  (multipart/x-mixed-replace; boundary=krouchiframe). هذا هو المسار
  الوحيد الذي يقبل رمز الربط معاملَ استعلام ?token= إلى جانب
  الترويسة — لأنه يُعرَض في عنصر <img> لا يستطيع ضبط الترويسات؛
  كل النقاط الأخرى بالترويسة حصراً. عدد البثوث النشطة يظهر في
  GET /api/status باسم "screen_viewers".
- POST /api/input {حدث إدخال واحد} → حقن فأرة/مفاتيح/نص على
  الحاسوب عبر remote.dispatch_input؛ حدث غير صالح = 400، ومنصّة
  لا تدعم الالتقاط/الحقن = 501.

الإصدار 3.3.2 — إطار الشاشة المفرد (من عائلة التحكّم أيضاً):
- GET  /api/screen/frame?w=&q= → {"image_b64", "format": "jpeg",
  "width", "height"}: إطار واحد لكل طلب بمصادقة الترويسة حصراً،
  يسحبه تطبيق الهاتف تباعاً عبر قناة طلباته العادية بدل بثّ MJPEG
  في <img> — لأن أصل التطبيق https وهمي (krouchi.local) فيحجب
  WebView البثَّ الصافي http:// كمختلط. طلبات الإطارات تُحسَب
  مشاهدةً في "screen_viewers" ما دام آخر إطار قبل أقلّ من 3 ثوانٍ.
  يبقى /api/screen/stream كما هو دون مساس.

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

import base64
import binascii
import json
import os
import queue
import secrets
import socket
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import control, remote
from .broker import PendingApprovals, request_summary
from .tasks import TaskManager, TaskStore, task_detail, task_summary

DEFAULT_PORT = 8765
TOKEN_MIN_CHARS = 12
MAX_BODY_BYTES = 1_000_000  # حدّ حجم جسم الطلب — طلبات الربط صغيرة بطبيعتها

# مفاتيح الإعدادات في جدول settings داخل قاعدة بيانات مجلد البيانات.
SETTING_TOKEN = "companion_token"
SETTING_PORT = "companion_port"
SETTING_AUTOSTART = "companion_autostart"

# ======================================================================
# قشرة تطبيق الويب (PWA): قائمة بيضاء ومكان المجلد
# ======================================================================
# ملفات القشرة المسموح بخدمتها كما هي، باسم الأساس ونوع المحتوى.
# أي اسم خارج هذه القائمة = 404 مهما كان موجوداً على القرص، فلا
# مجال لعبور المسارات (../) ولا لكشف ملفات المجلد الأخرى.
PWA_FILES = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "text/javascript; charset=utf-8",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "maskable-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
    # صور معرض أفاتار البوتات (assets/avatars في المصدر؛ تُخدَم من
    # مجلد القشرة pwa/avatars إن وُضعت فيه، وإلا من مجلد المعرض —
    # انظر static_file). الأسماء الستة حرفياً فقط: أي اسم آخر 404.
    "avatars/bot_1.png": "image/png",
    "avatars/bot_2.png": "image/png",
    "avatars/bot_3.png": "image/png",
    "avatars/bot_4.png": "image/png",
    "avatars/bot_5.png": "image/png",
    "avatars/bot_6.png": "image/png",
}

# متغيّر بيئة يتقدّم كل بحث تلقائي عن مجلد القشرة.
ENV_PWA_DIR = "KROUCHI_PWA_DIR"


def find_pwa_dir() -> Path | None:
    """يحدّد مجلد قشرة تطبيق الويب (pwa) إن وُجد، وإلا None.

    ترتيب البحث: متغيّر البيئة KROUCHI_PWA_DIR أولاً، ثم مجلد «pwa»
    بجانب حزمة krouchi_dz (جذر المشروع — ينطبق على شجرة المصدر وعلى
    الحزم إن ضمّن المُحزّم المجلد بجانب الحزمة)، ثم «pwa» داخل مجلد
    العمل الحالي. لا يُقبل المرشّح إلا إن احتوى index.html فعلاً.
    """
    candidates: list[Path] = []
    env_dir = os.environ.get(ENV_PWA_DIR)
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path(__file__).resolve().parent.parent / "pwa")
    candidates.append(Path.cwd() / "pwa")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _static_name_for_path(path: str) -> str | None:
    """اسم ملف القشرة المقابل لمسار طلب، أو None إن لم يطابق شكلاً مسموحاً.

    الأشكال المسموحة فقط: «/<file>» و«/app/<file>»، و«/» وحده يعني
    index.html، وصور المعرض «/avatars/<file>» و«/app/avatars/<file>»
    وتُرجع الاسم «avatars/<file>». الاسم نفسه يُفحص لاحقاً ضدّ
    القائمة البيضاء PWA_FILES قبل أي لمس للقرص، فمقاطع «..» لا تصل
    إلى نظام الملفات أبداً (مثل «avatars/../x» لا يطابق أي شكل هنا،
    وأسماء غير المعرض مثل «avatars/bot_99.png» تسقط في القائمة).
    """
    decoded = urllib.parse.unquote(path)
    segments = [seg for seg in decoded.split("/") if seg not in ("", ".")]
    if not segments:
        return "index.html"
    if len(segments) == 1:
        return segments[0]
    if len(segments) == 2 and segments[0] == "app":
        return segments[1]
    if len(segments) == 2 and segments[0] == "avatars":
        return f"avatars/{segments[1]}"
    if (
        len(segments) == 3
        and segments[0] == "app"
        and segments[1] == "avatars"
    ):
        return f"avatars/{segments[2]}"
    return None


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
        "task_id": request.task_id,
    }


class CompanionServer:
    """خادم HTTP للهاتف المرافق: بدء/إيقاف برمجي، ورمز ربط قابل للتبديل.

    engine_call: دالة (fn) -> نتيجة، تُنفّذ fn(engine) على خيط مالك
    المحرّك حاجبةً (انظر ترويسة الوحدة). registry: سجلّ الموافقات
    المعلّقة المشترك نفسه الذي يغذّي وسيط المحرّك وبطاقة الواجهة.
    pwa_dir: مجلد قشرة تطبيق الويب؛ None (الافتراضي) = بحث تلقائي
    عبر find_pwa_dir(). مسار صريح غير موجود يُعطّل القشرة فقط —
    واجهة /api/* تعمل في كل الحالات.
    """

    def __init__(
        self,
        engine_call,
        registry: PendingApprovals,
        token: str,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        pwa_dir: str | Path | None = None,
        control_root: str | Path | None = None,
        power_executor=None,
        open_executor=None,
        print_executor=None,
        printer_lister=None,
        clipboard_getter=None,
        clipboard_setter=None,
        volume_executor=None,
        window_lister=None,
        window_executor=None,
        process_lister=None,
        process_killer=None,
        screen_source=None,
        input_sink=None,
        file_max_bytes: int = control.FILE_MAX_BYTES,
        upload_max_bytes: int = control.UPLOAD_MAX_BYTES,
        task_engine_factory=None,
        task_workers: int = 2,
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
        if pwa_dir is not None:
            candidate = Path(pwa_dir)
            self.pwa_dir: Path | None = (
                candidate if (candidate / "index.html").is_file() else None
            )
        else:
            self.pwa_dir = find_pwa_dir()
        # -- تحكّم الهاتف بالحاسوب (الإصدار 3.2) -------------------------
        # جذر التحكّم ومنفّذات المنصّة كلها قابلة للحقن (الاختبارات
        # تستبدل الطباعة/الحافظة/الطاقة ببدائل وهمية فلا تلمس نظاماً).
        self.control_root = (
            Path(control_root).resolve()
            if control_root is not None
            else control.control_root()
        )
        self.power_executor = power_executor or control.default_power_executor
        self.open_executor = open_executor or control.open_target
        self.print_executor = print_executor or control.default_print_executor
        self.printer_lister = printer_lister or control.list_printers
        self.clipboard_getter = clipboard_getter or control.get_clipboard
        self.clipboard_setter = clipboard_setter or control.set_clipboard
        self.volume_executor = volume_executor or control.default_volume_executor
        self.window_lister = window_lister or control.list_windows
        self.window_executor = window_executor or control.default_window_executor
        self.process_lister = process_lister or control.list_processes
        self.process_killer = process_killer or control.default_process_killer
        # -- الشاشة الحية والإدخال عن بُعد (الإصدار 3.3) ------------------
        # مصدر الشاشة ومغرَز الإدخال (remote) يُنشآن كسولاً عند أول
        # استعمال ويُخزّنان هنا؛ قابلان للحقن من الاختبارات ببدائل
        # remote الوهمية (FakeScreenSource/FakeInputSink).
        self.screen_source = screen_source
        self.input_sink = input_sink
        self._screen_lock = threading.Lock()
        self._screen_viewers_count = 0
        # زمن آخر إطار مفرد خُدِم (/api/screen/frame — الإصدار 3.3.2):
        # ساحب الإطارات في تطبيق الهاتف يُحسَب مشاهداً ما دام الإطار
        # الأخير حديثاً (انظر خاصية screen_viewers).
        self._last_frame_at: float | None = None
        self.file_max_bytes = int(file_max_bytes)
        self.upload_max_bytes = int(upload_max_bytes)
        # -- مهام البوتات الخلفية ------------------------------------------
        self._task_engine_factory = task_engine_factory
        self._task_workers = int(task_workers)
        self.task_store: TaskStore | None = None
        self.task_manager: TaskManager | None = None

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
        if self.pwa_dir is None:
            print(
                "Krouchi_DZ companion server: no pwa/ web-app folder "
                "found — the static shell is disabled; the /api "
                "companion API keeps working. Set KROUCHI_PWA_DIR or "
                "place a pwa folder next to the krouchi_dz package "
                "to serve the web app."
            )
        self._start_tasks()

    # -- مهام البوتات الخلفية ------------------------------------------------
    def _default_task_engine_factory(self):
        """مصنع مهام افتراضي: محرّك جديد بنفس إعدادات محرّك المحادثة.

        تُقرأ الإعدادات من المحرّك الرئيسي عبر بوّابته (مجلد البيانات،
        ملف المزوّدين، النقل، مصنع المزوّدين، مهلة السؤال) فيرث كل
        مهمةٍ المفاتيح والمزوّدين أنفسهم — مع سجلّ الموافقات المشترك
        نفسه الذي يغذّي هذا الخادم.
        """
        registry = self.registry
        engine_call = self.engine_call

        def factory():
            from .engine import ChatEngine

            data_dir, providers_path, transport, provider_factory, timeout = (
                engine_call(
                    lambda e: (
                        e.data_dir,
                        e.providers_path,
                        e.transport,
                        e.provider_factory,
                        e.broker.ask_timeout,
                    )
                )
            )
            return ChatEngine(
                data_dir,
                providers_path=providers_path,
                ask_timeout=timeout,
                transport=transport,
                provider_factory=provider_factory,
                approval_registry=registry,
            )

        return factory

    def _start_tasks(self) -> None:
        """يفتح مخزن المهام على قاعدة المحرّك ويشغّل المشغّل ومراقبه.

        فشله لا يُسقط الخادم: تبقى بقية النقاط عاملة وتردّ نقاط
        المهام 503 حتى يُصلَح السبب.
        """
        if self.task_manager is not None:
            return
        try:
            db_path = self.engine_call(lambda e: str(e.db.path))
            self.task_store = TaskStore(db_path)
            factory = self._task_engine_factory or self._default_task_engine_factory()
            self.task_manager = TaskManager(
                self.task_store,
                factory,
                self.registry,
                workers=self._task_workers,
            )
            self.task_manager.start()
        except Exception as exc:
            print(f"Krouchi_DZ companion server: tasks disabled: {exc}")
            self.task_store = None
            self.task_manager = None

    # -- تحكّم الهاتف بالحاسوب -------------------------------------------------
    def is_control_enabled(self) -> bool:
        """إعداد control_enabled في قاعدة المحرّك (افتراضياً مفعَّل)."""
        try:
            value = self.engine_call(
                lambda e: e.db.get_setting("control_enabled", "true")
            )
        except Exception:
            return True  # تعذّرت القراءة — الافتراضي المعلن: مفعَّل
        return str(value).strip().lower() not in ("false", "0", "no", "off")

    def ask_control(
        self, action: str, params: dict, force_ask: bool = False
    ) -> bool:
        """يسأل عن فعل تحكّم عبر وسيط المحرّك الرئيسي وسجلّه المشترك.

        يمرّ عبر engine_call لأن الوسيط وسجلّ تدقيقه يعيشان على خيط
        مالك المحرّك؛ الانتظار هنا يحجب بوّابة المحرّك كما تفعل
        محادثة ask تماماً — سلوك متّسق مع بقية البرنامج.
        """
        decision = self.engine_call(
            lambda e: e.authorize_control(action, params, force_ask=force_ask)
        )
        return bool(decision.allowed)

    # -- الشاشة الحية والإدخال عن بُعد (الإصدار 3.3) -------------------------
    def get_screen_source(self):
        """مصدر الشاشة (remote): يُنشأ كسولاً عند أول استعمال ويُخزَّن."""
        with self._screen_lock:
            if self.screen_source is None:
                self.screen_source = remote.create_screen_source()
            return self.screen_source

    def get_input_sink(self):
        """مغرَز الإدخال (remote): يُنشأ كسولاً عند أول استعمال ويُخزَّن."""
        with self._screen_lock:
            if self.input_sink is None:
                self.input_sink = remote.create_input_sink()
            return self.input_sink

    @property
    def screen_viewers(self) -> int:
        """عدد مشاهدي الشاشة الآن (يظهر في GET /api/status): بثوث
        MJPEG النشطة + 1 ما دام آخر طلب إطار مفرد قبل أقلّ من 3
        ثوانٍ — ساحب الإطارات في تطبيق الهاتف (الإصدار 3.3.2) لا
        يُمسك اتصالاً مفتوحاً كالبثّ، فحداثة إطاره هي دليل المشاهدة."""
        with self._screen_lock:
            viewers = self._screen_viewers_count
            if (
                self._last_frame_at is not None
                and time.monotonic() - self._last_frame_at < 3.0
            ):
                viewers += 1
            return viewers

    def _note_screen_stream(self, delta: int) -> None:
        with self._screen_lock:
            self._screen_viewers_count = max(
                0, self._screen_viewers_count + delta
            )

    def _note_screen_frame(self) -> None:
        """يُسجّل زمن خدمة إطار مفرد الآن (لعدّاد screen_viewers)."""
        with self._screen_lock:
            self._last_frame_at = time.monotonic()

    # -- قشرة تطبيق الويب -------------------------------------------------
    def static_file(self, name: str) -> tuple[bytes, str] | None:
        """(محتوى، نوع) ملف قشرة باسم أساس، أو None إن لم يكن متاحاً.

        الاسم يجب أن يكون حرفياً أحد مفاتيح PWA_FILES — هذا هو حارس
        العبور الوحيد اللازم: الأسماء العادية لا تحتوي «/» أبداً،
        وأسماء المعرض هي الستة الحرفية «avatars/bot_N.png» فقط،
        فيُبنى المسار دائماً داخل مجلد القشرة نفسه (أو مجلد المعرض).
        صور المعرض: تُقرأ أولاً من «avatars/» داخل مجلد القشرة إن
        وُضعت هناك؛ فإن غابت قُرئت من مجلد المعرض الحقيقي
        (assets/avatars — انظر avatars.avatar_image_path) لأن
        المعرض يعيش هناك في شجرة المصدر لا داخل pwa/.
        """
        content_type = PWA_FILES.get(name)
        if content_type is None or self.pwa_dir is None:
            return None
        try:
            return (self.pwa_dir / name).read_bytes(), content_type
        except OSError:
            pass
        if name.startswith("avatars/"):
            from .avatars import avatar_image_path

            gallery_path = avatar_image_path(name[len("avatars/"):])
            if gallery_path is not None:
                try:
                    return gallery_path.read_bytes(), content_type
                except OSError:
                    return None
        return None

    def stop(self) -> None:
        """يوقف الخدمة ويحرّر المنفذ. لا شيء إن كان متوقّفاً أصلاً."""
        with self._state_lock:
            httpd, self._httpd = self._httpd, None
            self._thread = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self.task_manager is not None:
            self.task_manager.stop()
            self.task_manager = None
        if self.task_store is not None:
            try:
                self.task_store.close()
            except Exception:
                pass
            self.task_store = None

    # -- عمليات المحرّك (تُستدعى من معالج الطلبات) ---------------------------
    def list_bots(self) -> list[dict]:
        def job(engine):
            # الواجهة المشتركة هي الحقيقة عند الإرسال، فهي ما يُعرَض:
            # «provider»/«model» منها حين تُضبَط، وتراجع إلى قيم
            # البوت المخزَّنة حين لا واجهة مشتركة (الشكل لا يتغيّر).
            shared = engine.get_shared_api()
            bots = []
            for bot in engine.db.list_bots():
                if shared is not None:
                    provider_name, model = shared
                else:
                    cfg = engine.providers.get(bot["provider_name"])
                    provider_name = bot["provider_name"]
                    model = bot["model"] or (cfg.default_model if cfg else "")
                bots.append(
                    {
                        "id": bot["id"],
                        "name": bot["name"],
                        "provider": provider_name,
                        "model": model,
                        "mode": bot["approval_mode"],
                        # اسم ملف المعرض ("bot_3.png") أو "" ⇒ أحادي
                        # الحرف عند العميل؛ القيم القديمة تمرّ كما هي
                        # فيتعامل معها العميل كغير معرضية أيضاً.
                        "avatar": bot.get("avatar") or "",
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
    """يوجّه طلبات /api/* إلى الخادم المرافق بعد فحص رمز الربط،
    ويخدم قشرة تطبيق الويب الثابتة (GET فقط، بلا رمز) خارج /api/."""

    server_version = "Krouchi_DZ"

    @property
    def _srv(self) -> CompanionServer:
        return self.server.companion  # type: ignore[attr-defined]

    def log_message(self, format, *args):  # صمت: لا سجلّ طلبات على الطرفية
        pass

    # -- أدوات الردّ والقراءة ----------------------------------------------
    def _send_json(self, status: int, payload: dict) -> None:
        self._response_started = True
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        """يخدم ملف قشرة من القائمة البيضاء، أو 404 JSON كغيره."""
        name = _static_name_for_path(path)
        found = self._srv.static_file(name) if name is not None else None
        if found is None:
            return self._send_json(404, {"error": "مسار غير معروف"})
        body, content_type = found
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if name == "sw.js":
            # عامل الخدمة في الجذر أصلاً؛ الترويسة تصريح صريح بنطاقه
            self.send_header("Service-Worker-Allowed", "/")
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
            # خارج /api/: قشرة الويب الثابتة للقراءة فقط وبلا رمز؛
            # أي طريقة غير GET أو اسم خارج القائمة البيضاء = 404.
            if method == "GET":
                return self._serve_static(path)
            return self._send_json(404, {"error": "مسار غير معروف"})
        if not self._srv.check_token(self.headers.get("X-Krouchi-Token")):
            # الاستثناء الموثّق الوحيد من مصادقة الترويسة: بثّ الشاشة
            # (GET /api/screen/stream) يُعرَض في عنصر <img> لا يستطيع
            # ضبط الترويسات، فيُقبل رمز الربط معاملَ استعلام ?token=
            # لهذا المسار وحده وبهذه الطريقة وحدها؛ كل النقاط الأخرى
            # — وPOST على المسار نفسه ضمناً — بالترويسة حصراً.
            query_token = None
            if method == "GET" and path == "/api/screen/stream":
                query_token = (
                    urllib.parse.parse_qs(parsed.query).get("token")
                    or [None]
                )[0]
            if not self._srv.check_token(query_token):
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
            if isinstance(bot_id, str) and bot_id.strip().lstrip("-").isdigit():
                bot_id = int(bot_id)  # تسامح مع معرّف نصّي رقمي من عميل أقدم
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

        # ===== الإصدار 3.2: حالة الحاسوب =====
        if method == "GET" and path == "/api/status":
            from . import __version__  # متأخراً عمداً: يفكّ أي دورة استيراد

            payload = control.system_status(__version__)
            payload["screen_viewers"] = srv.screen_viewers  # الإصدار 3.3
            return self._send_json(200, payload)

        # ===== الإصدار 3.2: مهام البوتات (لا يمسّها control_enabled) =====
        if path == "/api/tasks" or path.startswith("/api/tasks/"):
            return self._route_tasks(method, path)

        # ===== الإصدار 3.2: عائلة التحكّم (تُعطَّل بـ control_enabled) =====
        if path in (
            "/api/files", "/api/file", "/api/run", "/api/open",
            "/api/screenshot", "/api/power", "/api/printers",
            "/api/print", "/api/upload", "/api/clipboard",
            "/api/volume", "/api/windows", "/api/window",
            "/api/processes", "/api/process/kill",
            "/api/screen/stream", "/api/screen/frame", "/api/input",
        ):
            if not srv.is_control_enabled():
                return self._send_json(403, {"error": "control disabled"})
            return self._route_control(method, path, parsed)

        return self._send_json(404, {"error": "مسار غير معروف"})

    # -- مهام البوتات ---------------------------------------------------------
    def _route_tasks(self, method: str, path: str) -> None:
        srv = self._srv
        if srv.task_manager is None or srv.task_store is None:
            return self._send_json(503, {"error": "المهام غير متاحة"})
        manager, store = srv.task_manager, srv.task_store

        if method == "POST" and path == "/api/tasks":
            try:
                body = self._read_json_body()
            except ValueError as exc:
                return self._send_json(400, {"error": f"جسم غير صالح: {exc}"})
            bot_id = body.get("bot_id")
            if isinstance(bot_id, str) and bot_id.strip().lstrip("-").isdigit():
                bot_id = int(bot_id)  # نفس تسامح /api/chat مع المعرّفات النصية
            title = body.get("title")
            prompt = body.get("prompt")
            if (
                not isinstance(bot_id, int)
                or isinstance(bot_id, bool)
                or not isinstance(title, str)
                or not title.strip()
                or not isinstance(prompt, str)
                or not prompt.strip()
            ):
                return self._send_json(
                    400,
                    {"error": "الحقول المطلوبة: bot_id (رقم) و title و prompt"},
                )
            bot = srv.engine_call(lambda e: e.db.get_bot(bot_id))
            if bot is None:
                return self._send_json(404, {"error": "بوت غير موجود"})
            task = manager.submit(bot_id, title.strip(), prompt)
            return self._send_json(
                201,
                {
                    "task": {
                        "id": task["id"],
                        "bot_id": task["bot_id"],
                        "title": task["title"],
                        "status": task["status"],
                        "created_at": task["created_at"],
                    }
                },
            )

        if method == "GET" and path == "/api/tasks":
            tasks = [task_summary(t) for t in store.list_tasks()]
            return self._send_json(200, {"tasks": tasks})

        rest = path[len("/api/tasks/"):]
        parts = rest.split("/")
        if not parts[0].isdigit():
            return self._send_json(404, {"error": "مسار غير معروف"})
        task_id = int(parts[0])

        if method == "GET" and len(parts) == 1:
            task = store.get_task(task_id)
            if task is None:
                return self._send_json(404, {"error": "مهمة غير موجودة"})
            return self._send_json(200, {"task": task_detail(task)})

        if method == "POST" and len(parts) == 2 and parts[1] == "cancel":
            outcome = manager.cancel(task_id)
            if outcome == "not_found":
                return self._send_json(404, {"error": "مهمة غير موجودة"})
            if outcome == "final":
                return self._send_json(
                    409, {"error": "المهمة منتهية أصلاً فلا تُلغى"}
                )
            return self._send_json(200, {"ok": True})

        return self._send_json(404, {"error": "مسار غير معروف"})

    # -- تحكّم الهاتف بالحاسوب ---------------------------------------------------
    def _route_control(self, method: str, path: str, parsed) -> None:
        """درع عائلة التحكّم: أي استثناء يفلت من منفّذ/قائمة منصّة يصير
        500 JSON بدل إسقاط الاتصال على الهاتف (حدث فعلياً مع قائمة
        نوافذ فاشلة: «Connection reset»). الردّ يُرسَل فقط إن لم يكن
        شيء قد أُرسل بعد — بثّ الشاشة مثلاً يرسل ترويساته بنفسه.
        التعيينات الخاصة داخل الجسم (400/501/الموافقات) تبقى كما هي
        لأنها تُرسَل ردوداً ولا ترفع استثناءات.
        """
        try:
            self._route_control_body(method, path, parsed)
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception as exc:
            if not getattr(self, "_response_started", False):
                try:
                    self._send_json(500, {"error": str(exc)})
                except Exception:
                    pass

    def _route_control_body(self, method: str, path: str, parsed) -> None:
        srv = self._srv
        root = srv.control_root
        query = urllib.parse.parse_qs(parsed.query)

        if method == "GET" and path == "/api/files":
            raw = (query.get("path") or [""])[0]
            target = control.resolve_within_root(root, raw)
            if target is None:
                return self._send_json(403, {"error": "المسار خارج جذر التحكّم"})
            if not target.is_dir():
                return self._send_json(404, {"error": "مجلد غير موجود"})
            try:
                payload = control.list_dir(root, target)
            except OSError as exc:
                return self._send_json(500, {"error": f"تعذّرت القراءة: {exc}"})
            return self._send_json(200, payload)

        if method == "GET" and path == "/api/file":
            raw = (query.get("path") or [""])[0]
            target = control.resolve_within_root(root, raw)
            if target is None:
                return self._send_json(403, {"error": "المسار خارج جذر التحكّم"})
            if not target.is_file():
                return self._send_json(404, {"error": "ملف غير موجود"})
            size = target.stat().st_size
            if size > srv.file_max_bytes:
                return self._send_json(413, {"error": "الملف أكبر من الحدّ المسموح"})
            try:
                data = target.read_bytes()
            except OSError as exc:
                return self._send_json(500, {"error": f"تعذّرت القراءة: {exc}"})
            return self._send_json(
                200,
                {
                    "name": target.name,
                    "size": size,
                    "content_b64": base64.b64encode(data).decode("ascii"),
                },
            )

        if method == "GET" and path == "/api/screenshot":
            shot = control.take_screenshot()
            if shot is None:
                return self._send_json(
                    501, {"error": "لقطة الشاشة غير متاحة على هذا النظام"}
                )
            data, fmt = shot
            return self._send_json(
                200,
                {"image_b64": base64.b64encode(data).decode("ascii"), "format": fmt},
            )

        if method == "GET" and path == "/api/screen/stream":
            return self._serve_screen_stream(query)

        if method == "GET" and path == "/api/screen/frame":
            return self._serve_screen_frame(query)

        if method == "POST" and path == "/api/input":
            body, error = self._body_or_400()
            if error is not None:
                return error
            try:
                size = srv.get_screen_source().size()
            except RuntimeError as exc:
                return self._send_json(501, {"error": str(exc)})
            try:
                result = remote.dispatch_input(
                    srv.get_input_sink(), size, body
                )
            except ValueError as exc:  # حدث غير صالح — رسالة عربية من remote
                return self._send_json(400, {"error": str(exc)})
            except RuntimeError as exc:  # منصّة لا تدعم الحقن
                return self._send_json(501, {"error": str(exc)})
            return self._send_json(200, result)

        if method == "GET" and path == "/api/printers":
            return self._send_json(200, {"printers": srv.printer_lister()})

        if method == "GET" and path == "/api/clipboard":
            return self._send_json(200, {"text": srv.clipboard_getter()})

        if method == "POST" and path == "/api/run":
            body, error = self._body_or_400()
            if error is not None:
                return error
            command = body.get("command")
            if not isinstance(command, str) or not command.strip():
                return self._send_json(400, {"error": "الحقل المطلوب: command"})
            if not srv.ask_control("run_command", {"command": command}):
                return self._send_json(403, {"error": "denied"})
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=control.RUN_TIMEOUT,
                )
                return self._send_json(
                    200,
                    {
                        "exit": proc.returncode,
                        "stdout": (proc.stdout or "")[-control.OUTPUT_TAIL:],
                        "stderr": (proc.stderr or "")[-control.OUTPUT_TAIL:],
                        "timed_out": False,
                    },
                )
            except subprocess.TimeoutExpired as exc:
                out = exc.stdout if isinstance(exc.stdout, str) else ""
                err = exc.stderr if isinstance(exc.stderr, str) else ""
                return self._send_json(
                    200,
                    {
                        "exit": None,
                        "stdout": out[-control.OUTPUT_TAIL:],
                        "stderr": err[-control.OUTPUT_TAIL:],
                        "timed_out": True,
                    },
                )
            except OSError as exc:
                return self._send_json(502, {"error": f"تعذّر التنفيذ: {exc}"})

        if method == "POST" and path == "/api/open":
            body, error = self._body_or_400()
            if error is not None:
                return error
            target = body.get("target")
            if not isinstance(target, str) or not target.strip():
                return self._send_json(400, {"error": "الحقل المطلوب: target"})
            if not srv.ask_control("open_target", {"target": target}):
                return self._send_json(403, {"error": "denied"})
            try:
                srv.open_executor(target)
            except Exception as exc:
                return self._send_json(502, {"error": f"تعذّر الفتح: {exc}"})
            return self._send_json(200, {"ok": True})

        if method == "POST" and path == "/api/power":
            body, error = self._body_or_400()
            if error is not None:
                return error
            action = body.get("action")
            if action not in control.POWER_ACTIONS:
                return self._send_json(
                    400,
                    {"error": "action يجب أن تكون إحدى: "
                     + "، ".join(control.POWER_ACTIONS)},
                )
            # الطاقة تُسأل دائماً — force_ask ولو كان السياق full
            if not srv.ask_control("power", {"action": action}, force_ask=True):
                return self._send_json(403, {"error": "denied"})
            try:
                srv.power_executor(action)
            except Exception as exc:
                return self._send_json(502, {"error": f"تعذّر التنفيذ: {exc}"})
            return self._send_json(
                200,
                {"ok": True, "scheduled_in_s": control.POWER_SCHEDULED_S[action]},
            )

        if method == "POST" and path == "/api/volume":
            # الصوت غير مؤذٍّ: بلا وسيط موافقات (كرمز الربط وبوّابة التحكّم فقط)
            body, error = self._body_or_400()
            if error is not None:
                return error
            action = body.get("action")
            if action not in control.VOLUME_ACTIONS:
                return self._send_json(
                    400, {"error": "action يجب أن تكون up أو down أو mute"}
                )
            try:
                srv.volume_executor(action)
            except Exception as exc:
                return self._send_json(
                    501, {"error": f"تحكّم الصوت غير متاح: {exc}"}
                )
            return self._send_json(200, {"ok": True})

        if method == "GET" and path == "/api/windows":
            return self._send_json(200, {"windows": srv.window_lister()})

        if method == "POST" and path == "/api/window":
            body, error = self._body_or_400()
            if error is not None:
                return error
            window_id = body.get("id")
            if isinstance(window_id, str) and window_id.strip().lstrip("-").isdigit():
                window_id = int(window_id)
            action = body.get("action")
            if (
                not isinstance(window_id, int)
                or isinstance(window_id, bool)
                or action not in control.WINDOW_ACTIONS
            ):
                return self._send_json(
                    400,
                    {"error": "الحقول المطلوبة: id (رقم) و action "
                     "(focus|minimize|maximize|close)"},
                )
            params = {"id": window_id, "action": action}
            if not srv.ask_control("window_control", params):
                return self._send_json(403, {"error": "denied"})
            try:
                srv.window_executor(window_id, action)
            except Exception as exc:
                return self._send_json(502, {"error": f"تعذّر التحكّم بالنافذة: {exc}"})
            return self._send_json(200, {"ok": True})

        if method == "GET" and path == "/api/processes":
            return self._send_json(200, {"processes": srv.process_lister()})

        if method == "POST" and path == "/api/process/kill":
            body, error = self._body_or_400()
            if error is not None:
                return error
            pid = body.get("pid")
            if isinstance(pid, str) and pid.strip().isdigit():
                pid = int(pid)
            if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                return self._send_json(400, {"error": "الحقل المطلوب: pid (رقم موجب)"})
            if not srv.ask_control("kill_process", {"pid": pid}):
                return self._send_json(403, {"error": "denied"})
            try:
                srv.process_killer(pid)
            except Exception as exc:
                return self._send_json(502, {"error": f"فشل إنهاء العملية: {exc}"})
            return self._send_json(200, {"ok": True})

        if method == "POST" and path == "/api/print":
            body, error = self._body_or_400()
            if error is not None:
                return error
            raw_path = body.get("path")
            printer = body.get("printer")
            if not isinstance(raw_path, str) or not raw_path.strip():
                return self._send_json(400, {"error": "الحقل المطلوب: path"})
            if printer is not None and not isinstance(printer, str):
                return self._send_json(400, {"error": "printer يجب أن تكون نصاً"})
            target = control.resolve_within_root(root, raw_path)
            if target is None:
                return self._send_json(403, {"error": "المسار خارج جذر التحكّم"})
            if not target.is_file():
                return self._send_json(404, {"error": "ملف غير موجود"})
            params = {"path": str(target), "printer": printer or ""}
            if not srv.ask_control("print_file", params):
                return self._send_json(403, {"error": "denied"})
            try:
                srv.print_executor(str(target), printer)
            except Exception as exc:
                return self._send_json(502, {"error": f"فشلت الطباعة: {exc}"})
            return self._send_json(200, {"ok": True})

        if method == "POST" and path == "/api/upload":
            body, error = self._body_or_400()
            if error is not None:
                return error
            raw_path = body.get("path")
            content_b64 = body.get("content_b64")
            if not isinstance(raw_path, str) or not raw_path.strip():
                return self._send_json(400, {"error": "الحقل المطلوب: path"})
            if not isinstance(content_b64, str):
                return self._send_json(400, {"error": "الحقل المطلوب: content_b64"})
            target = control.resolve_within_root(root, raw_path)
            if target is None:
                return self._send_json(403, {"error": "المسار خارج جذر التحكّم"})
            try:
                data = base64.b64decode(content_b64, validate=True)
            except (binascii.Error, ValueError):
                return self._send_json(400, {"error": "content_b64 غير صالح"})
            if len(data) > srv.upload_max_bytes:
                return self._send_json(413, {"error": "الملف أكبر من الحدّ المسموح"})
            params = {"path": str(target), "size": len(data)}
            if not srv.ask_control("upload_file", params):
                return self._send_json(403, {"error": "denied"})
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except OSError as exc:
                return self._send_json(500, {"error": f"تعذّرت الكتابة: {exc}"})
            return self._send_json(200, {"ok": True, "size": len(data)})

        if method == "POST" and path == "/api/clipboard":
            body, error = self._body_or_400()
            if error is not None:
                return error
            text = body.get("text")
            if not isinstance(text, str):
                return self._send_json(400, {"error": "الحقل المطلوب: text"})
            if not srv.ask_control("set_clipboard", {"text": text}):
                return self._send_json(403, {"error": "denied"})
            try:
                srv.clipboard_setter(text)
            except Exception as exc:
                return self._send_json(502, {"error": f"تعذّر ضبط الحافظة: {exc}"})
            return self._send_json(200, {"ok": True})

        return self._send_json(404, {"error": "مسار غير معروف"})

    def _body_or_400(self):
        """يقرأ جسم JSON أو يرسل 400 — يعيد (body, None) أو (None, None بعد الإرسال)."""
        try:
            return self._read_json_body(), None
        except ValueError as exc:
            self._send_json(400, {"error": f"جسم غير صالح: {exc}"})
            return None, True

    def _serve_screen_frame(self, query) -> None:
        """إطار واحد من شاشة الحاسوب: JPEG داخل JSON (base64).

        بديل بثّ MJPEG لتطبيق الهاتف (الإصدار 3.3.2): التطبيق يخدم
        واجهته من أصل https وهمي (https://krouchi.local/) ولا يضبط
        وضع المحتوى المختلط، فيحجب WebView بثّ <img> الصافي http://
        كمختلط — والبثّ هو الميزة الوحيدة المحمَّلة كمورد ويب فرعي؛
        كل ما عداه يمرّ عبر الجسر الأصيل فيعمل. فيسحب التطبيق
        الإطارات واحداً واحداً عبر هذه النقطة بقناة الطلبات العادية
        نفسها (مصادقة الترويسة حصراً — لا استثناء ?token= هنا).
        المعاملات: w (أقصى عرض، 1280 افتراضياً، بين 320 و1920)،
        q (جودة JPEG، 60، بين 30 و90) — بنفس أسلوب تحليل البثّ.
        مصدر غير مدعوم على هذه المنصّة = 501. كل إطار يُخدَم
        يُسجَّل زمنه عند الخادم لعدّاد screen_viewers في /api/status.
        """
        srv = self._srv

        def _param(name: str, default: int, low: int, high: int) -> int:
            raw = (query.get(name) or [""])[0]
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        max_width = _param("w", 1280, 320, 1920)
        quality = _param("q", 60, 30, 90)
        source = srv.get_screen_source()
        try:
            width, height = source.size()
            data = source.grab_jpeg(max_width=max_width, quality=quality)
        except RuntimeError as exc:
            return self._send_json(501, {"error": str(exc)})
        srv._note_screen_frame()
        return self._send_json(
            200,
            {
                "image_b64": base64.b64encode(data).decode("ascii"),
                "format": "jpeg",
                "width": width,
                "height": height,
            },
        )

    def _serve_screen_stream(self, query) -> None:
        """بثّ شاشة الحاسوب إلى الهاتف: MJPEG بأجزاء multipart متتابعة.

        معاملات الاستعلام: w (أقصى عرض، 1280 افتراضياً، بين 320
        و1920)، q (جودة JPEG، 60، بين 30 و90)، fps (‏10، بين 1
        و20). مصدر غير مدعوم على هذه المنصّة = 501 قبل بدء البث.
        إغلاق الهاتف للاتصال نهاية طبيعية صامتة؛ وعدّاد المشاهدين
        على الخادم يُرفع عند البدء ويُخفَض في finally مهما حدث.
        (سجلّ الطلبات صامت أصلاً في هذا المعالج — log_message فارغة.)
        """
        srv = self._srv

        def _param(name: str, default: int, low: int, high: int) -> int:
            raw = (query.get(name) or [""])[0]
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        max_width = _param("w", 1280, 320, 1920)
        quality = _param("q", 60, 30, 90)
        fps = _param("fps", 10, 1, 20)
        source = srv.get_screen_source()
        try:
            source.size()  # فحص قدرة فعلي قبل أي ترويسة: غير المدعوم = 501
        except RuntimeError as exc:
            return self._send_json(501, {"error": str(exc)})
        boundary = remote.DEFAULT_BOUNDARY.decode("ascii")
        self.send_response(200)
        self.send_header(
            "Content-Type", f"multipart/x-mixed-replace; boundary={boundary}"
        )
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self._response_started = True
        srv._note_screen_stream(+1)
        interval = 1.0 / fps
        try:
            for frame in remote.iter_mjpeg_frames(
                source, max_width=max_width, quality=quality
            ):
                started = time.monotonic()
                self.wfile.write(remote.mjpeg_part(frame))
                self.wfile.flush()
                delay = interval - (time.monotonic() - started)
                if delay > 0:
                    time.sleep(delay)
        except (BrokenPipeError, ConnectionResetError):
            pass  # أغلق الهاتف البث — نهاية طبيعية صامتة
        except RuntimeError:
            pass  # تعطّل المصدر أثناء البث: لا خطأ يُرسل بعد الترويسات
        finally:
            srv._note_screen_stream(-1)
