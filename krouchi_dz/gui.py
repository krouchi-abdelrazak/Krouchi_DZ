"""الواجهة الرسومية في Krouchi_DZ (الخطوة 2) — Tkinter، مكتبة قياسية فقط.

تطبيق محادثة عربي: قائمة بوتات كجهات اتصال على اليمين، محادثة البوت
المحدّد في الوسط، شاشة «إدخال API» (أي عنوان + أي مفتاح ⇒ جلب النماذج)،
وبطاقات موافقة مشروطة تربط ردّ نداء وسيط الموافقات بأزرار فعلية.

الخيوط (مهم): قاعدة SQLite في المحرّك مربوطة بخيط إنشائها، فلا يُلمس
المحرّك إلا من خيط واحد مخصّص يملكه EngineRunner؛ الواجهة ترسل «مهام»
(دوال تأخذ المحرّك) عبر طابور، والنتائج تعود عبر طابور إتمام يُسلَّم
في حلقة Tk — فلا تتجمّد الواجهة أبداً ولا تُخترق سلامة الخيوط.
وطلبات الموافقة (ask) تمرّ بسجلّ مشترك واحد (PendingApprovals يملكه
_ApprovalBridge): الوسيط يسجّل الطلب وينتظر حسمه، والواجهة تجسّ السجلّ
وتفتح بطاقة الموافقة لأقدم طلب، وخادم مرافقة الهاتف (server.py) يحسم
من السجلّ نفسه — غياب الحسم قبل المهلة = رفض (فشل مُغلق) في كل الحالات.

اللغات: كل نصّ ظاهر في الواجهة يمرّ عبر i18n.t — العربية (افتراضية،
اتجاه RTL وقائمة جانبية على اليمين) والإنجليزية (LTR وقائمة على
اليسار)، والتبديل من القائمة الجانبية نفسها يعيد بناء النافذة دون
إعادة تشغيل العملية، ويُحفَظ الاختيار في إعدادات قاعدة البيانات.
"""

from __future__ import annotations

import ipaddress
import json
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk

from . import autostart, i18n
from .avatars import (
    GALLERY_FILES,
    avatar_image_path,
    display_avatar_text,
    find_avatars_dir,
    is_gallery_avatar,
    monogram_for_name,
)
from .broker import ApprovalRequest, PendingApprovals, request_summary
from .engine import ChatEngine, default_data_dir
from .i18n import t
from .tasks import ACTIVE_STATUSES, FINAL_STATUSES, TaskStore
from .server import (
    SETTING_AUTOSTART,
    SETTING_PORT,
    CompanionServer,
    get_or_create_token,
    lan_ips,
    regenerate_token,
)
from .server import DEFAULT_PORT as SERVER_DEFAULT_PORT

# -- ثوابت الواجهة ---------------------------------------------------------
ASK_TIMEOUT = 120.0     # مهلة وسيط الموافقات داخل المحرّك (ثوانٍ)
DIALOG_TIMEOUT = 115    # بطاقة الموافقة تُغلق ذاتياً (رفض) قبل ذلك
BRIDGE_WAIT = 118.0     # انتظار الجسر لجواب الواجهة — أقل من مهلة الوسيط
POLL_MS = 60            # دورة جسّ الطوابير في حلقة Tk (ملي ثانية)

APPROVAL_MODES_ORDER = ("ask", "full", "readonly")

# مفتاح إعداد «التحكم الكلي من الهاتف» وقيم تعطيله — كما يقرؤهما
# server.CompanionServer.is_control_enabled حرفياً (افتراضيه مفعَّل).
SETTING_CONTROL_ENABLED = "control_enabled"
_CONTROL_OFF_VALUES = ("false", "0", "no", "off")

# نطاق عناوين Tailscale (CGNAT): 100.64.0.0/10.
_TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def control_setting_enabled(raw) -> bool:
    """يفسّر قيمة إعداد control_enabled بمنطق الخادم نفسه حرفياً.

    غياب الإعداد (None) يعني الافتراضي «true» أي مفعَّل؛ والقيمة
    معطِّلة فقط إن كانت — بعد التشذيب وخفض الأحرف — إحدى قيم الإيقاف.
    """
    if raw is None:
        raw = "true"
    return str(raw).strip().lower() not in _CONTROL_OFF_VALUES


def ip_label(ip: str) -> str:
    """العنوان كما يُعرض في قوائم العناوين: مع لاحقة " (Tailscale)"
    إن كان ضمن نطاق Tailscale 100.64.0.0/10، وإلا العنوان نفسه."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if address in _TAILSCALE_NETWORK:
        return f"{ip} (Tailscale)"
    return ip


# -- تسميات مترجمة (تُحسَب بلغة الواجهة الحالية عند كل استعمال) --------------
def mode_label(mode: str) -> str:
    """تسمية نمط الموافقة بلغة الواجهة (النط نفسه إن كان غريباً)."""
    key = f"mode.{mode}"
    return t(key) if i18n.has(key) else mode


def mode_by_label(label: str) -> str:
    """يعكس mode_label: من التسمية المعروضة إلى النمط (افتراضيه ask)."""
    for mode in APPROVAL_MODES_ORDER:
        if mode_label(mode) == label:
            return mode
    return "ask"


def action_label(action: str) -> str:
    """تسمية الإجراء بلغة الواجهة (الاسم نفسه إن كان غير معروف)."""
    key = f"action.{action}"
    return t(key) if i18n.has(key) else action


def decision_label(decision: str) -> str:
    """تسمية القرار بلغة الواجهة (الاسم نفسه إن كان غير معروف)."""
    key = f"decision.{decision}"
    return t(key) if i18n.has(key) else decision


def task_status_label(status: str) -> str:
    """تسمية حالة مهمة بلغة الواجهة (الحالة نفسها إن كانت غير معروفة)."""
    key = f"taskstatus.{status}"
    return t(key) if i18n.has(key) else status


# -- مساعدات اتجاه التخطيط ----------------------------------------------------
def _text_anchor() -> str:
    """مرساة النصوص: يمين في العربية (e)، يسار في الإنجليزية (w)."""
    return "e" if i18n.is_rtl() else "w"


def _start_side() -> str:
    """جهة «البداية» في الاتجاه الحالي: اليمين للعربية، اليسار للإنجليزية."""
    return "right" if i18n.is_rtl() else "left"


def _end_side() -> str:
    """جهة «النهاية» في الاتجاه الحالي (عكس جهة البداية)."""
    return "left" if i18n.is_rtl() else "right"


def _set_window_icon(root: tk.Tk) -> None:
    """أيقونة النافذة الرئيسية (شعار KA) من icon.png بجانب هذه الوحدة.

    تُتخطّى بصمت إن غاب الملف أو تعذّرت قراءته — الأيقونة تجميلية
    ولا يجوز أن تُسقط التطبيق أبداً.
    """
    try:
        icon_path = Path(__file__).with_name("icon.png")
        if not icon_path.is_file():
            return
        image = tk.PhotoImage(file=str(icon_path))
        root.iconphoto(True, image)
        root._ka_icon_image = image  # مرجع يمنع جمع الصورة من الذاكرة
    except Exception:
        pass


def _load_avatar_thumbnail(path: Path, size: int = 48):
    """صورة Tk مصغّرة (~size بكسل) لملف أفاتار، أو None عند أي فشل.

    يُفضَّل Pillow (ImageTk) مع تصغير فعلي؛ فإن غاب يُستعمل
    tk.PhotoImage مع subsample صحيح (أكبر عامل يقسّم الأبعاد إلى
    ~size). أي فشل قراءة/تحويل يعيد None فيعرض المستدعي بلاطة
    بديلة محايدة — الصورة تجميلية ولا يجوز أن تُسقط حواراً أبداً.
    """
    try:
        from PIL import Image, ImageTk

        with Image.open(path) as image:
            image.thumbnail((size, size))
            return ImageTk.PhotoImage(image.copy())
    except ImportError:
        pass  # لا Pillow — جرّب PhotoImage الأصلي تحت
    except Exception:
        return None
    try:
        image = tk.PhotoImage(file=str(path))
        factor = max(
            1,
            max(image.width(), image.height()) // size,
        )
        if factor > 1:
            image = image.subsample(factor, factor)
        return image
    except Exception:
        return None



# ======================================================================
# مشغّل المحرّك: خيط واحد يملك المحرّك ويُسلسِل كل الوصول إليه
# ======================================================================
class EngineRunner:
    """يُنشئ المحرّك داخل خيطه ويُنفّذ المهام المرسلة إليه بالتتابع.

    submit(fn, on_done): fn تأخذ المحرّك وتعيد قيمة؛ on_done(ok, value)
    يُستدعى في خيط الواجهة (عبر attach + poll). call(fn): صورة حاجبة
    مخصّصة للاختبارات والأدوات — لا تُستعمل من معالجات الواجهة.
    """

    def __init__(self, engine_factory):
        self._factory = engine_factory
        self.engine: ChatEngine | None = None
        self._jobs: queue.Queue = queue.Queue()
        self._done: queue.Queue = queue.Queue()
        self._callbacks: dict[int, object] = {}
        self._counter = 0
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._init_error: Exception | None = None
        self._root: tk.Misc | None = None
        self._thread = threading.Thread(
            target=self._loop, name="krouchi-engine", daemon=True
        )
        self._thread.start()

    def _loop(self) -> None:
        try:
            engine = self._factory()
        except Exception as exc:  # فشل إنشاء المحرّك يُبلَّغ ولا ينهار الخيط صامتاً
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
            job_id, fn, direct = job
            try:
                result = (job_id, True, fn(engine))
            except Exception as exc:
                result = (job_id, False, exc)
            if direct:
                # تسليم مباشر في خيط المحرّك: ردّ النداء هنا لا يلمس
                # الودجتات (يضبط حدثاً فقط) — انظر call_blocking.
                callback = self._callbacks.pop(job_id, None)
                if callback is not None:
                    try:
                        callback(result[1], result[2])
                    except Exception:
                        pass
            else:
                self._done.put(result)

    # -- إرسال المهام ------------------------------------------------------
    def submit(self, fn, on_done=None, _direct: bool = False) -> int:
        with self._lock:
            self._counter += 1
            job_id = self._counter
        if on_done is not None:
            self._callbacks[job_id] = on_done
        self._jobs.put((job_id, fn, _direct))
        return job_id

    def call(self, fn, timeout: float = 30.0):
        """ينفّذ مهمة وينتظر نتيجتها (للاختبارات فقط — يحجب الخيط المنادي)."""
        import time

        event = threading.Event()
        holder: dict = {}

        def _cb(ok, value):
            holder["ok"] = ok
            holder["value"] = value
            event.set()

        self.submit(fn, _cb)
        # أثناء الانتظار نسلّم أي إتمامات أخرى جاهزة (قد تخصّ واجهات مفتوحة).
        deadline = time.monotonic() + timeout
        while not event.is_set():
            self.poll()
            if time.monotonic() > deadline:
                raise TimeoutError(t("err.job_timeout"))
            event.wait(0.02)
        if holder["ok"]:
            return holder["value"]
        raise holder["value"]

    def call_blocking(self, fn, timeout: float | None = None):
        """ينفّذ مهمة وينتظر نتيجتها دون جسّ الطابور بنفسه (لخيوط الخادم).

        على خلاف call() لا يستدعي poll() إطلاقاً: تُسلَّم نتيجته
        مباشرة في خيط المحرّك (ردّ النداء يضبط حدثاً فقط ولا يلمس
        أي ويدجت)، فيعمل من أي خيط حتى قبل أن تدور حلقة الواجهة —
        آمن لخادم مرافقة الهاتف ولمهيّئاته التي تعمل عند الإقلاع.
        """
        event = threading.Event()
        holder: dict = {}

        def _cb(ok, value):
            holder["ok"] = ok
            holder["value"] = value
            event.set()

        self.submit(fn, _cb, _direct=True)
        if not event.wait(timeout):
            raise TimeoutError(t("err.job_timeout"))
        if holder["ok"]:
            return holder["value"]
        raise holder["value"]

    # -- تسليم الإتمامات في خيط الواجهة --------------------------------------
    def poll(self) -> None:
        """يسلّم كل الإتمامات الجاهزة لردود ندائها (يُستدعى من خيط الواجهة)."""
        while True:
            try:
                job_id, ok, value = self._done.get_nowait()
            except queue.Empty:
                return
            callback = self._callbacks.pop(job_id, None)
            if callback is not None:
                callback(ok, value)

    def attach(self, root: tk.Misc) -> None:
        """يربط التسليم بحلقة Tk: جسّ دوري تلقائي لطابور الإتمامات."""
        self._root = root
        self._tk_poll()

    def _tk_poll(self) -> None:
        self.poll()
        if self._root is not None:
            try:
                self._root.after(POLL_MS, self._tk_poll)
            except tk.TclError:
                self._root = None

    def wait_ready(self, timeout: float = 15.0) -> None:
        """ينتظر اكتمال إنشاء المحرّك داخل خيطه؛ يرفع خطأ الإنشاء إن وقع."""
        if not self._ready.wait(timeout):
            raise TimeoutError(t("err.engine_slow"))
        if self._init_error is not None:
            raise self._init_error

    def shutdown(self) -> None:
        self._root = None
        self._callbacks.clear()
        self._jobs.put(None)


# ======================================================================
# جسر الموافقات: سجلّ مشترك بين المحرّك والواجهة وخادم الهاتف
# ======================================================================
class _ApprovalBridge:
    """يملك سجلّ الموافقات المعلّقة المشترك (PendingApprovals).

    السجلّ هو نقطة الالتقاء الوحيدة: وسيط المحرّك يسجّل طلبات نمط ask
    فيه وينتظر حسمها (مباشرة في الإنتاج، أو عبر ask() هنا في مسار ردّ
    النداء)، والواجهة تعرض بطاقة لأقدم طلب معلّق وتحسمه فيه، وخادم
    مرافقة الهاتف يحسم من السجلّ نفسه — فالحسم من أي جهة يُنهي
    الانتظار عند كل الجهات. لا يلمس قاعدة البيانات إطلاقاً.
    """

    def __init__(self, registry: PendingApprovals | None = None):
        self.registry = registry if registry is not None else PendingApprovals()

    def ask(self, request: ApprovalRequest) -> bool:
        """مسار ردّ النداء: يسجّل الطلب في السجلّ وينتظر حسمه.

        يعمل في خيط فرعي يولّده الوسيط داخل خيط المحرّك. انقضاء
        الانتظار دون حسم = False (فشل مُغلق) ويُسحَب الطلب من السجلّ،
        قبل مهلة الوسيط نفسه.
        """
        item = self.registry.create(request)
        if not item.event.wait(BRIDGE_WAIT):
            self.registry.expire(item.id)
            return False
        return bool(item.decision)


# ======================================================================
# بطاقة الموافقة
# ======================================================================
def describe_target(request: ApprovalRequest) -> str:
    """نصّ هدف الإجراء كما سيُعرض على المستخدم (مسار/أمر + معاينة كتابة).

    التنفيذ نفسه في broker.request_summary — مصدر واحد للنصّ تستعمله
    بطاقة الموافقة هنا وملخّصات خادم الهاتف على حدّ سواء.
    """
    return request_summary(request)


class ApprovalDialog:
    """نافذة موافقة مشروطة: بوت يطلب إجراءً — موافقة أو رفض.

    تُستعمل بطريقتين: show() الحاجبة (تعيد True/False)، أو بردّ نداء
    on_answer في الواجهة الرئيسية. الإغلاق من زرّ النافذة أو انتهاء
    العدّاد (timeout ثانية) = رفض دائماً — فشل مُغلق.
    """

    def __init__(
        self,
        parent: tk.Misc,
        request: ApprovalRequest,
        on_answer=None,
        timeout: int = DIALOG_TIMEOUT,
    ):
        self.request = request
        self.on_answer = on_answer
        self.result: bool | None = None
        self._answered = False
        self._remaining = int(timeout)
        self.action_text = action_label(request.action)
        self.target_text = describe_target(request)

        top = tk.Toplevel(parent)
        self.top = top
        top.title(t("approval.title"))
        top.transient(parent)
        top.resizable(False, False)

        tk.Label(
            top,
            text=t("approval.asks", bot=request.bot_name),
            font=("TkDefaultFont", 11, "bold"),
            anchor=_text_anchor(),
        ).pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(
            top, text=t("approval.action", action=self.action_text),
            anchor=_text_anchor(),
        ).pack(fill="x", padx=14)
        tk.Label(
            top,
            text=self.target_text,
            anchor=_text_anchor(),
            justify="right" if i18n.is_rtl() else "left",
            wraplength=480,
            relief="sunken",
            borderwidth=1,
            padx=8,
            pady=6,
        ).pack(fill="x", padx=14, pady=8)
        self.countdown_label = tk.Label(
            top, text="", anchor=_text_anchor(), fg="#b71c1c"
        )
        self.countdown_label.pack(fill="x", padx=14)

        buttons = tk.Frame(top)
        buttons.pack(fill="x", padx=14, pady=(4, 12))
        self.deny_button = tk.Button(
            buttons, text=t("common.deny"), width=12, command=self.deny
        )
        self.deny_button.pack(side="left")
        self.allow_button = tk.Button(
            buttons, text=t("common.allow"), width=12, command=self.allow
        )
        self.allow_button.pack(side="right")

        top.protocol("WM_DELETE_WINDOW", self._on_close)
        self.allow_button.focus_set()
        self._update_countdown()
        # إمساك (grab) مؤجّل ومحروس: wait_visibility قد يحجب للأبد إن كان
        # الجذر مسحوباً (بيئات بلا مدير نوافذ) — لا نعتمد عليه أبداً.
        try:
            top.after(10, self._try_grab)
            top.after(1000, self._tick)
        except tk.TclError:
            pass

    def _try_grab(self) -> None:
        try:
            self.top.grab_set()
        except tk.TclError:
            pass  # بلا إمساك في البيئات مقطوعة الشاشة — الحوار يعمل على أي حال

    # -- القرار (يحدث مرة واحدة فقط) ---------------------------------------
    def _finish(self, value: bool) -> None:
        if self._answered:
            return
        self._answered = True
        self.result = value
        if self.on_answer is not None:
            self.on_answer(value)
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def allow(self) -> None:
        self._finish(True)

    def deny(self) -> None:
        self._finish(False)

    def _on_close(self) -> None:
        """إغلاق النافذة من النظام = رفض (فشل مُغلق)."""
        self._finish(False)

    # -- العدّاد -------------------------------------------------------------
    def _update_countdown(self) -> None:
        self.countdown_label.config(
            text=t("approval.countdown", seconds=self._remaining)
        )

    def _tick(self) -> None:
        if self._answered:
            return
        self._remaining -= 1
        if self._remaining <= 0:
            self._finish(False)
            return
        self._update_countdown()
        try:
            self.top.after(1000, self._tick)
        except tk.TclError:
            pass

    def show(self) -> bool:
        """يعرض البطاقة حاجباً حتى القرار؛ يعيد True للسماح فقط."""
        self.top.wait_window()
        return bool(self.result)


# ======================================================================
# شاشة إدخال API
# ======================================================================
class AddApiDialog:
    """«إدخال API»: أي عنوان + أي مفتاح ⇒ اكتشاف النماذج بنفسه.

    تعرض أيضاً قائمة المزوّدين المسجّلين مع حالة التحقق لكلٍّ منهم.
    كل اتصال بالمحرك يمرّ عبر EngineRunner — بلا شبكة في خيط الواجهة.
    """

    def __init__(self, parent: tk.Misc, runner: EngineRunner, on_providers_changed=None):
        self.runner = runner
        self.on_providers_changed = on_providers_changed
        self.fetch_finished = False
        self.discovery_result = None
        self.providers_loaded = False
        self._provider_names: list[str] = []

        top = tk.Toplevel(parent)
        self.top = top
        top.title(t("addapi.title"))
        top.transient(parent)
        top.geometry("620x560")

        tk.Label(
            top, text=t("addapi.providers"), anchor=_text_anchor(),
            font=("TkDefaultFont", 10, "bold"),
        ).pack(fill="x", padx=12, pady=(10, 2))
        self.providers_list = tk.Listbox(top, height=6)
        self.providers_list.pack(fill="x", padx=12)
        prov_buttons = tk.Frame(top)
        prov_buttons.pack(fill="x", padx=12, pady=(4, 8))
        tk.Button(
            prov_buttons, text=t("addapi.fetch_selected"),
            command=self.fetch_selected_models,
        ).pack(side=_start_side())
        tk.Button(
            prov_buttons, text=t("addapi.refresh_list"),
            command=self.refresh_providers,
        ).pack(side=_start_side(), padx=6)

        form = tk.Frame(top)
        form.pack(fill="x", padx=12)
        self.name_var = tk.StringVar()
        self.url_var = tk.StringVar()
        self.key_var = tk.StringVar()
        self._field(form, t("addapi.name"), self.name_var, row=0)
        self._field(form, t("addapi.base_url"), self.url_var, row=1)
        self._field(form, t("addapi.key"), self.key_var, row=2, show="•")

        self.fetch_button = tk.Button(
            top, text=t("addapi.fetch"), command=self.start_fetch,
            font=("TkDefaultFont", 11, "bold"),
        )
        self.fetch_button.pack(pady=(10, 4))
        self.status_label = tk.Label(
            top, text="", anchor=_text_anchor(),
            justify="right" if i18n.is_rtl() else "left",
            wraplength=580, fg="#37474f",
        )
        self.status_label.pack(fill="x", padx=12)
        tk.Label(top, text=t("addapi.models"), anchor=_text_anchor()).pack(
            fill="x", padx=12, pady=(6, 2)
        )
        self.models_list = tk.Listbox(top, height=7)
        self.models_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.refresh_providers()

    @staticmethod
    def _field(parent, label: str, var: tk.StringVar, row: int, show: str | None = None):
        rtl = i18n.is_rtl()
        label_col, entry_col = (1, 0) if rtl else (0, 1)
        tk.Label(parent, text=label, anchor=_text_anchor()).grid(
            row=row, column=label_col, sticky=_text_anchor(), pady=3
        )
        entry = tk.Entry(parent, textvariable=var, justify="left", width=52)
        if show:
            entry.config(show=show)
        entry.grid(
            row=row, column=entry_col, sticky="ew", pady=3,
            padx=(0, 8) if rtl else (8, 0),
        )
        parent.columnconfigure(entry_col, weight=1)
        return entry

    # -- قائمة المزوّدين ------------------------------------------------------
    def refresh_providers(self) -> None:
        def job(engine):
            return [
                (
                    cfg.name,
                    cfg.base_url,
                    cfg.verified,
                    engine.provider_configured(cfg.name),
                )
                for cfg in engine.providers.values()
            ]

        def done(ok, rows):
            if not ok:
                self.status_label.config(
                    text=t("addapi.err_providers", error=rows)
                )
                return
            self._provider_names = [r[0] for r in rows]
            self.providers_list.delete(0, "end")
            for name, base_url, verified, configured in rows:
                state = t("addapi.verified") if verified else t("addapi.unverified")
                key_state = t("addapi.key_saved") if configured else t("addapi.no_key")
                self.providers_list.insert(
                    "end", f"{name} — {base_url} — {state} — {key_state}"
                )
            self.providers_loaded = True

        self.runner.submit(job, done)

    # -- جلب النماذج -----------------------------------------------------------
    def _begin_fetch(self, job) -> None:
        self.fetch_finished = False
        self.discovery_result = None
        self.fetch_button.config(state="disabled")
        self.status_label.config(text=t("addapi.connecting"))
        self.models_list.delete(0, "end")
        self.runner.submit(job, self._fetch_done)

    def _fetch_done(self, ok, value) -> None:
        self.fetch_finished = True
        self.fetch_button.config(state="normal")
        if not ok:
            self.status_label.config(text=t("common.err_unexpected", error=value))
            return
        result = value
        self.discovery_result = result
        if result.ok:
            for model in result.models:
                self.models_list.insert("end", model)
            note = t("addapi.from_cache") if result.from_cache else ""
            self.status_label.config(
                text=t(
                    "addapi.success",
                    provider=result.provider,
                    count=len(result.models),
                )
                + note
            )
        else:
            # رسالة المحرّك العربية كما هي — بلا تجميل ولا إخفاء.
            self.status_label.config(text=result.error)
        self.refresh_providers()
        if self.on_providers_changed is not None:
            self.on_providers_changed()

    def start_fetch(self) -> None:
        """زرّ «اجلب النماذج»: يسجّل المزوّد من العنوان+المفتاح ويكتشفه."""
        base_url = self.url_var.get().strip()
        api_key = self.key_var.get().strip()
        name = self.name_var.get().strip() or None
        if not base_url or not api_key:
            self.status_label.config(text=t("addapi.need_fields"))
            self.fetch_finished = True
            return

        def job(engine):
            return engine.add_api(base_url, api_key, name=name)

        self._begin_fetch(job)

    def fetch_selected_models(self) -> None:
        """يعيد جلب نماذج المزوّد المحدّد في القائمة (تجاوزاً للكاش)."""
        selection = self.providers_list.curselection()
        if not selection:
            self.status_label.config(text=t("addapi.need_selection"))
            return
        provider_name = self._provider_names[selection[0]]

        def job(engine):
            return engine.fetch_models(provider_name, force=True)

        self._begin_fetch(job)


# ======================================================================
# حوار الواجهة المشتركة: API واحدة لكل البوتات، تُدخَل مرة واحدة
# ======================================================================
class SharedApiDialog:
    """«الواجهة المشتركة»: مزوّد واحد + نموذج واحد يعمل بهما كل البوتات.

    منتقي المزوّد من engine.providers، ومنتقي النموذج يُملأ عبر
    engine.fetch_models (من الكاش إن كان حديثاً؛ وزرّ التحديث يجبر
    الجلب بـ force=True) — بنمط خيوط AddApiDialog نفسه عبر
    EngineRunner، فلا شبكة في خيط الواجهة. الاختيار الحالي للواجهة
    المشتركة يُفتتَح محدَّداً، والحفظ عبر engine.set_shared_api.
    """

    def __init__(self, parent: tk.Misc, runner: EngineRunner, on_saved=None):
        self.runner = runner
        self.on_saved = on_saved
        self.saved = False
        self.providers_loaded = False
        self.models_loaded = False
        self._shared: tuple[str, str] | None = None

        top = tk.Toplevel(parent)
        self.top = top
        top.title(t("sharedapi.title"))
        top.transient(parent)
        top.geometry("520x300")

        tk.Label(
            top, text=t("sharedapi.hint"), anchor=_text_anchor(),
            wraplength=480, justify="right" if i18n.is_rtl() else "left",
            fg="#37474f",
        ).pack(fill="x", padx=12, pady=(10, 4))

        form = tk.Frame(top)
        form.pack(fill="x", padx=12)
        rtl = i18n.is_rtl()
        lc, ec = (1, 0) if rtl else (0, 1)  # عمود التسمية وعمود الإدخال
        anchor = _text_anchor()
        epadx = (0, 8) if rtl else (8, 0)
        self.provider_var = tk.StringVar()
        self.model_var = tk.StringVar()
        tk.Label(form, text=t("sharedapi.provider"), anchor=anchor).grid(
            row=0, column=lc, sticky=anchor, pady=4
        )
        self.provider_combo = ttk.Combobox(
            form, textvariable=self.provider_var, state="readonly"
        )
        self.provider_combo.grid(row=0, column=ec, sticky="ew", pady=4, padx=epadx)
        self.provider_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._fetch_models()
        )
        tk.Label(form, text=t("sharedapi.model"), anchor=anchor).grid(
            row=1, column=lc, sticky=anchor, pady=4
        )
        model_frame = tk.Frame(form)
        model_frame.grid(row=1, column=ec, sticky="ew", pady=4, padx=epadx)
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var)
        self.model_combo.pack(side=_start_side(), fill="x", expand=True)
        tk.Button(
            model_frame, text=t("common.refresh"),
            command=lambda: self._fetch_models(force=True),
        ).pack(side=_end_side(), padx=(6, 0) if not rtl else (0, 6))
        form.columnconfigure(ec, weight=1)

        self.status_label = tk.Label(
            top, text=t("bot.loading"), anchor=anchor, fg="#37474f",
            wraplength=480, justify="right" if i18n.is_rtl() else "left",
        )
        self.status_label.pack(fill="x", padx=12, pady=(6, 0))
        buttons = tk.Frame(top)
        buttons.pack(fill="x", padx=12, pady=10)
        tk.Button(
            buttons, text=t("common.cancel"), width=10, command=top.destroy
        ).pack(side="left")
        tk.Button(
            buttons, text=t("common.save"), width=10,
            font=("TkDefaultFont", 10, "bold"), command=self.save,
        ).pack(side="right")

        self._load_providers()

    # -- التحميل ---------------------------------------------------------------
    def _load_providers(self) -> None:
        def job(engine):
            return list(engine.providers), engine.get_shared_api()

        def done(ok, value):
            if not ok:
                self.status_label.config(text=t("bot.err_load", error=value))
                return
            names, shared = value
            self._shared = shared
            self.provider_combo.config(values=names)
            if shared is not None and shared[0] in names:
                self.provider_var.set(shared[0])
            elif names:
                self.provider_var.set(names[0])
            self.providers_loaded = True
            self.status_label.config(text="")
            if self.provider_var.get():
                self._fetch_models()

        self.runner.submit(job, done)

    def _fetch_models(self, force: bool = False) -> None:
        provider = self.provider_var.get().strip()
        if not provider:
            return
        self.models_loaded = False
        self.status_label.config(text=t("sharedapi.fetching"))

        def job(engine):
            return engine.fetch_models(provider, force=force)

        def done(ok, result):
            if not ok:
                self.status_label.config(
                    text=t("common.err_unexpected", error=result)
                )
                return
            self.models_loaded = True
            if not result.ok:
                # رسالة المحرّك العربية كما هي — بلا تجميل ولا إخفاء.
                self.status_label.config(text=result.error)
                return
            self.model_combo.config(values=list(result.models))
            shared = self._shared
            if (
                shared is not None
                and shared[0] == provider
                and shared[1]
            ):
                # الاختيار الحالي للواجهة المشتركة يبقى محدَّداً.
                self.model_var.set(shared[1])
            elif result.models and self.model_var.get() not in result.models:
                self.model_var.set(result.models[0])
            self.status_label.config(text="")

        self.runner.submit(job, done)

    # -- الحفظ ------------------------------------------------------------------
    def save(self) -> None:
        provider = self.provider_var.get().strip()
        model = self.model_var.get().strip()
        if not provider:
            self.status_label.config(text=t("bot.need_provider"))
            return

        def job(engine):
            engine.set_shared_api(provider, model)

        def done(ok, value):
            if not ok:
                self.status_label.config(text=t("bot.err_save", error=value))
                return
            self.saved = True
            if self.on_saved is not None:
                self.on_saved()
            self.top.destroy()

        self.status_label.config(text=t("bot.saving"))
        self.runner.submit(job, done)


# ======================================================================
# نافذة إنشاء / تعديل بوت
# ======================================================================
class BotDialog:
    """نموذج بوت: اسم، تعليمات نظام، نمط موافقة (افتراضيه اسأل).

    لا منتقي مزوّد/نموذج هنا بعد (v3.4): كل البوتات تعمل بواجهة
    API مشتركة واحدة تُدخَل مرة واحدة — يعرض النموذج سطراً للقراءة
    فقط بالواجهة الحالية وزرّاً يفتح حوارها (SharedApiDialog).
    عند إنشاء بوت جديد يحفظ المحرّك لقطة اسم مزوّد الواجهة
    المشتركة في سجلّه؛ والتعديل لا يمسّ المزوّد/النموذج المخزَّنين.

    وصورة أفاتار من المعرض: صفّ بلاطات مصغّرة (الصور الستّ في
    assets/avatars) + بلاطة «بلا صورة» تعرض أحادي حرف الاسم؛ القيمة
    المختارة اسم ملف معرض أو "" (أحادي). قيمة قديمة غير معرضية
    (إيموجي) تُفتتح على «بلا صورة» لأنها ليست ملف معرض.
    """

    def __init__(
        self,
        parent: tk.Misc,
        runner: EngineRunner,
        bot: dict | None = None,
        on_saved=None,
    ):
        self.runner = runner
        self.bot = bot
        self.on_saved = on_saved
        self.saved = False
        self.shared_loaded = False
        self.shared_api: tuple[str, str] | None = None
        self._shared_dialog: SharedApiDialog | None = None
        self._avatar_images: list = []  # مراجع تمنع جمع الصور من الذاكرة
        self._avatar_buttons: dict[str, tk.Button] = {}

        top = tk.Toplevel(parent)
        self.top = top
        top.title(t("bot.edit_title") if bot else t("bot.new_title"))
        top.transient(parent)
        top.geometry("560x520")

        form = tk.Frame(top)
        form.pack(fill="both", expand=True, padx=12, pady=10)
        self.name_var = tk.StringVar(value=(bot or {}).get("name", ""))
        self.mode_var = tk.StringVar(
            value=mode_label((bot or {}).get("approval_mode", "ask"))
        )
        initial_avatar = (bot or {}).get("avatar", "")
        self.avatar_var = tk.StringVar(
            value=initial_avatar if is_gallery_avatar(initial_avatar) else ""
        )

        rtl = i18n.is_rtl()
        lc, ec = (1, 0) if rtl else (0, 1)  # عمود التسمية وعمود الإدخال
        anchor = _text_anchor()
        epadx = (0, 8) if rtl else (8, 0)
        tk.Label(form, text=t("bot.name"), anchor=anchor).grid(
            row=0, column=lc, sticky=anchor, pady=4
        )
        tk.Entry(form, textvariable=self.name_var).grid(
            row=0, column=ec, sticky="ew", pady=4, padx=epadx
        )
        # الواجهة المشتركة: سطر قراءة فقط بالوضع الحالي + زرّ تغييرها.
        self.shared_label = tk.Label(form, text="", anchor=anchor)
        self.shared_label.grid(
            row=1, column=ec, sticky="ew", pady=4, padx=epadx
        )
        tk.Button(
            form, text=t("bot.shared_change"), command=self.open_shared_api
        ).grid(row=2, column=ec, sticky="ew", pady=4, padx=epadx)
        tk.Label(form, text=t("bot.mode"), anchor=anchor).grid(
            row=3, column=lc, sticky=anchor, pady=4
        )
        ttk.Combobox(
            form,
            textvariable=self.mode_var,
            values=[mode_label(m) for m in APPROVAL_MODES_ORDER],
            state="readonly",
        ).grid(row=3, column=ec, sticky="ew", pady=4, padx=epadx)
        tk.Label(
            form,
            text="صورة البوت:" if rtl else "Bot picture:",
            anchor=anchor,
        ).grid(row=4, column=lc, sticky="n" + anchor, pady=4)
        self.avatar_frame = tk.Frame(form)
        self.avatar_frame.grid(
            row=4, column=ec, sticky="ew", pady=4, padx=epadx
        )
        self._build_avatar_picker()
        tk.Label(form, text=t("bot.prompt"), anchor=anchor).grid(
            row=5, column=lc, sticky="n" + anchor, pady=4
        )
        self.prompt_text = tk.Text(form, height=5, wrap="word")
        self.prompt_text.grid(row=5, column=ec, sticky="ew", pady=4, padx=epadx)
        if bot and bot.get("system_prompt"):
            self.prompt_text.insert("1.0", bot["system_prompt"])
        form.columnconfigure(ec, weight=1)

        self.status_label = tk.Label(
            top, text=t("bot.loading"), anchor=anchor, fg="#37474f"
        )
        self.status_label.pack(fill="x", padx=12)
        buttons = tk.Frame(top)
        buttons.pack(fill="x", padx=12, pady=10)
        tk.Button(
            buttons, text=t("common.cancel"), width=10, command=top.destroy
        ).pack(side="left")
        tk.Button(
            buttons, text=t("common.save"), width=10,
            font=("TkDefaultFont", 10, "bold"), command=self.save,
        ).pack(side="right")

        self._load_shared()

    # -- منتقي صورة البوت (المعرض) ------------------------------------------
    def _build_avatar_picker(self) -> None:
        """يبني صفّ البلاطات: صور المعرض الستّ + بلاطة «بلا صورة».

        ملف/مجلد غائب أو تحميل فاشل ⇒ بلاطة بديلة محايدة تحمل رقم
        الصورة، والاختيار يبقى ممكناً (القيمة تُحفَظ ولو غاب الملف
        هنا — قد يوجد على جهاز آخر). النقر يختار ويُبرز المختار.
        """
        avatars_dir = find_avatars_dir()
        for index, filename in enumerate(GALLERY_FILES, start=1):
            image = None
            if avatars_dir is not None:
                candidate = avatars_dir / filename
                if candidate.is_file():
                    image = _load_avatar_thumbnail(candidate)
            if image is not None:
                self._avatar_images.append(image)
                button = tk.Button(
                    self.avatar_frame,
                    image=image,
                    command=lambda f=filename: self.select_avatar(f),
                )
            else:
                button = tk.Button(
                    self.avatar_frame,
                    text=str(index),
                    width=4,
                    height=2,
                    command=lambda f=filename: self.select_avatar(f),
                )
            button.pack(side="left", padx=2, pady=2)
            self._avatar_buttons[filename] = button
        # بلاطة «بلا صورة»: معاينة أحادي حرف الاسم الحالي.
        self.monogram_button = tk.Button(
            self.avatar_frame,
            text=monogram_for_name(self.name_var.get()),
            width=4,
            height=2,
            font=("TkDefaultFont", 14, "bold"),
            command=lambda: self.select_avatar(""),
        )
        self.monogram_button.pack(side="left", padx=(8, 2), pady=2)
        self._avatar_buttons[""] = self.monogram_button
        # حرف المعاينة يتبع الاسم أثناء الكتابة.
        try:
            self.name_var.trace_add("write", self._refresh_monogram_tile)
        except tk.TclError:
            pass
        self._refresh_avatar_highlight()

    def _refresh_monogram_tile(self, *_args) -> None:
        try:
            self.monogram_button.config(
                text=monogram_for_name(self.name_var.get())
            )
        except tk.TclError:
            pass

    def _refresh_avatar_highlight(self) -> None:
        selected = self.avatar_var.get()
        for value, button in self._avatar_buttons.items():
            try:
                button.config(
                    relief="sunken" if value == selected else "raised",
                    borderwidth=3 if value == selected else 1,
                )
            except tk.TclError:
                pass

    def select_avatar(self, value: str) -> None:
        """يختار قيمة أفاتار (اسم ملف معرض أو "" لبلا صورة) ويُبرزها."""
        self.avatar_var.set(value if is_gallery_avatar(value) else "")
        self._refresh_avatar_highlight()

    # -- الواجهة المشتركة ------------------------------------------------------
    def _load_shared(self) -> None:
        """يقرأ الواجهة المشتركة الحالية ويعرضها في سطر القراءة فقط."""

        def job(engine):
            return engine.get_shared_api()

        def done(ok, value):
            if not ok:
                self.status_label.config(text=t("bot.err_load", error=value))
                return
            self.shared_api = value
            if value is None:
                text = t("bot.shared_unset")
            elif value[1]:
                text = t(
                    "bot.shared_current", provider=value[0], model=value[1]
                )
            else:
                text = t("bot.shared_no_model", provider=value[0])
            self.shared_label.config(text=text)
            self.shared_loaded = True
            self.status_label.config(text="")

        self.runner.submit(job, done)

    def open_shared_api(self) -> None:
        """يفتح حوار الواجهة المشتركة؛ حفظه يعيد تحميل سطر العرض هنا."""
        self._shared_dialog = SharedApiDialog(
            self.top, self.runner, on_saved=self._load_shared
        )

    # -- الحفظ ------------------------------------------------------------------
    def save(self) -> None:
        name = self.name_var.get().strip()
        mode = mode_by_label(self.mode_var.get())
        prompt = self.prompt_text.get("1.0", "end").strip()
        avatar = self.avatar_var.get()
        if not name:
            self.status_label.config(text=t("bot.need_name"))
            return
        bot_id = (self.bot or {}).get("id")

        def job(engine):
            if bot_id is None:
                # بلا مزوّد: المحرّك يحفظ لقطة مزوّد الواجهة المشتركة.
                return engine.create_bot(
                    name,
                    system_prompt=prompt,
                    avatar=avatar,
                    approval_mode=mode,
                )
            # التعديل لا يمسّ المزوّد/النموذج المخزَّنين إطلاقاً.
            engine.db.update_bot(
                bot_id,
                name=name,
                system_prompt=prompt,
                avatar=avatar,
                approval_mode=mode,
            )
            return bot_id

        def done(ok, value):
            if not ok:
                self.status_label.config(text=t("bot.err_save", error=value))
                return
            self.saved = True
            if self.on_saved is not None:
                self.on_saved()
            self.top.destroy()

        self.status_label.config(text=t("bot.saving"))
        self.runner.submit(job, done)


# ======================================================================
# نافذة سجلّ التدقيق
# ======================================================================
class AuditWindow:
    """جدول قرارات وسيط الموافقات من قاعدة البيانات (الأحدث أولاً)."""

    def __init__(self, parent: tk.Misc, runner: EngineRunner):
        self.runner = runner
        self.rows_loaded = False

        top = tk.Toplevel(parent)
        self.top = top
        top.title(t("audit.title"))
        top.transient(parent)
        top.geometry("760x420")

        columns = ("time", "bot", "action", "decision", "reason")
        self.tree = ttk.Treeview(top, columns=columns, show="headings")
        for col, title, width in (
            ("time", t("audit.col_time"), 170),
            ("bot", t("audit.col_bot"), 110),
            ("action", t("audit.col_action"), 90),
            ("decision", t("audit.col_decision"), 80),
            ("reason", t("audit.col_reason"), 300),
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor=_text_anchor())
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Button(top, text=t("common.refresh"), command=self.refresh).pack(
            pady=(0, 10)
        )
        self.refresh()

    def refresh(self) -> None:
        def job(engine):
            names = {b["id"]: b["name"] for b in engine.db.list_bots()}
            rows = []
            for row in engine.db.get_audit():
                rows.append(
                    (
                        row["created_at"],
                        names.get(row["bot_id"], f"#{row['bot_id']}"),
                        action_label(row["action"]),
                        decision_label(row["decision"]),
                        row["reason"],
                    )
                )
            rows.reverse()  # الأحدث أولاً
            return rows

        def done(ok, rows):
            if not ok:
                return
            for item in self.tree.get_children():
                self.tree.delete(item)
            for row in rows:
                self.tree.insert("", "end", values=row)
            self.rows_loaded = True

        self.runner.submit(job, done)


# ======================================================================
# نافذة مهام البوتات
# ======================================================================
class TasksWindow:
    """مهام البوتات الخلفية من جدول tasks: قائمة وحالة وتفاصيل وإلغاء.

    القراءة عبر EngineRunner: مهمة تفتح TaskStore على ملف قاعدة
    المحرّك نفسه (اتصاله الخاص الآمن بين الخيوط، وقائمته تصل اسم
    البوت من جدول bots) وتعيد الصفوف. والإلغاء يمرّ — عبر مهمة
    Runner أيضاً — بمدير مهام الخادم نفسه (TaskManager.cancel، نقطة
    الدخول التي تستعملها نقطة POST /api/tasks/<id>/cancel) حين يكون
    متاحاً؛ فإن غاب (الخادم متوقّف فلا عمال أصلاً) يُختم الإلغاء في
    المخزن مباشرة بمنطق فرع «في الانتظار» نفسه في TaskManager.cancel.
    """

    def __init__(
        self,
        parent: tk.Misc,
        runner: EngineRunner,
        server: CompanionServer | None = None,
    ):
        self.runner = runner
        self.server = server
        self.rows_loaded = False
        self.tasks: list[dict] = []
        self._tasks_by_id: dict[int, dict] = {}

        top = tk.Toplevel(parent)
        self.top = top
        top.title(t("tasks.title"))
        top.transient(parent)
        top.geometry("760x540")

        columns = ("title", "bot", "status", "created")
        self.tree = ttk.Treeview(top, columns=columns, show="headings")
        for col, title, width in (
            ("title", t("tasks.col_title"), 250),
            ("bot", t("tasks.col_bot"), 120),
            ("status", t("tasks.col_status"), 110),
            ("created", t("tasks.col_created"), 180),
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor=_text_anchor())
        self.tree.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.empty_label = tk.Label(
            top, text="", anchor=_text_anchor(), fg="#757575"
        )
        self.empty_label.pack(fill="x", padx=10)

        detail = tk.Frame(top)
        detail.pack(fill="x", padx=10, pady=(4, 0))
        self.prompt_text = self._detail_block(detail, t("tasks.prompt"), 0, 3)
        self.result_text = self._detail_block(detail, t("tasks.result"), 1, 3)
        self.error_text = self._detail_block(detail, t("tasks.error"), 2, 2)

        buttons = tk.Frame(top)
        buttons.pack(fill="x", padx=10, pady=10)
        self.cancel_button = tk.Button(
            buttons,
            text=t("tasks.cancel"),
            command=self.cancel_task,
            state="disabled",
        )
        self.cancel_button.pack(side="left")
        tk.Button(
            buttons, text=t("common.refresh"), command=self.refresh
        ).pack(side="right")
        self.refresh()

    @staticmethod
    def _detail_block(parent, label: str, row: int, height: int) -> tk.Text:
        tk.Label(parent, text=label, anchor=_text_anchor()).grid(
            row=row * 2, column=0, sticky=_text_anchor(), pady=(4, 0)
        )
        widget = tk.Text(parent, height=height, wrap="word", state="disabled")
        widget.grid(row=row * 2 + 1, column=0, sticky="ew")
        parent.columnconfigure(0, weight=1)
        return widget

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)
        widget.config(state="disabled")

    # -- القائمة ---------------------------------------------------------------
    def refresh(self) -> None:
        def job(engine):
            store = TaskStore(engine.db.path)
            try:
                rows = store.list_tasks()
            finally:
                store.close()
            names = {b["id"]: b["name"] for b in engine.db.list_bots()}
            for row in rows:
                if not row.get("bot_name"):
                    row["bot_name"] = names.get(
                        row["bot_id"], f"#{row['bot_id']}"
                    )
            return rows

        def done(ok, rows):
            if not ok:
                return
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.tasks = rows
            self._tasks_by_id = {row["id"]: row for row in rows}
            for row in rows:
                self.tree.insert(
                    "",
                    "end",
                    iid=str(row["id"]),
                    values=(
                        row["title"],
                        row["bot_name"],
                        task_status_label(row["status"]),
                        row["created_at"],
                    ),
                )
            self.empty_label.config(
                text=t("tasks.empty") if not rows else ""
            )
            self.rows_loaded = True
            self._on_select()

        self.runner.submit(job, done)

    # -- التحديد والتفاصيل -------------------------------------------------------
    def _selected_task(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            task_id = int(selection[0])
        except (TypeError, ValueError):
            return None
        return self._tasks_by_id.get(task_id)

    def _on_select(self, _event=None) -> None:
        task = self._selected_task()
        self._set_text(self.prompt_text, (task or {}).get("prompt") or "")
        self._set_text(self.result_text, (task or {}).get("result") or "")
        self._set_text(self.error_text, (task or {}).get("error") or "")
        active = task is not None and task["status"] in ACTIVE_STATUSES
        self.cancel_button.config(state="normal" if active else "disabled")

    # -- الإلغاء --------------------------------------------------------------------
    def cancel_task(self) -> None:
        task = self._selected_task()
        if task is None or task["status"] not in ACTIVE_STATUSES:
            return
        task_id = task["id"]
        manager = self.server.task_manager if self.server is not None else None

        def job(engine):
            if manager is not None:
                # نقطة الدخول نفسها التي تستعملها نقطة الإلغاء في الخادم.
                return manager.cancel(task_id)
            store = TaskStore(engine.db.path)
            try:
                current = store.get_task(task_id)
                if current is None:
                    return "not_found"
                if current["status"] in FINAL_STATUSES:
                    return "final"
                if store.set_status_if(task_id, ACTIVE_STATUSES, "cancelled"):
                    store.update_task(
                        task_id,
                        finished_at=datetime.now(timezone.utc).isoformat(),
                    )
                    store.append_log(
                        task_id, "cancelled", "أُلغيت من واجهة الحاسوب"
                    )
                    return "ok"
                return "final"
            finally:
                store.close()

        def done(ok, value):
            self.refresh()

        self.runner.submit(job, done)


# ======================================================================
# نافذة ربط الهاتف (خادم المرافقة)
# ======================================================================
class PhoneLinkDialog:
    """«ربط الهاتف»: حالة خادم المرافقة وعناوينه ورمز الربط والتحكّم به.

    بدء/إيقاف الخادم وتدوير رمزه عمليات محلية فورية (لا تلمس المحرّك)؛
    تجديد الرمز يُحفَظ في إعدادات القاعدة عبر EngineRunner أولاً ثم
    يسري على الخادم، وخيار التشغيل التلقائي يُحفَظ في الإعدادات نفسها.
    """

    def __init__(self, parent: tk.Misc, runner: EngineRunner, server: CompanionServer):
        self.runner = runner
        self.server = server
        self._closed = False
        self._screen_after: str | None = None

        top = tk.Toplevel(parent)
        self.top = top
        top.title(t("phone.title"))
        top.transient(parent)
        top.geometry("580x640")

        anchor = _text_anchor()
        justify = "right" if i18n.is_rtl() else "left"
        tk.Label(
            top,
            text=t("phone.heading"),
            anchor=anchor,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(
            top,
            text=t("phone.desc"),
            anchor=anchor,
            justify=justify,
            wraplength=545,
            fg="#37474f",
        ).pack(fill="x", padx=14)

        self.status_label = tk.Label(
            top, text="", anchor=anchor, font=("TkDefaultFont", 11, "bold")
        )
        self.status_label.pack(fill="x", padx=14, pady=(10, 2))
        self.address_label = tk.Label(
            top, text="", anchor=anchor, justify=justify, fg="#1565c0"
        )
        self.address_label.pack(fill="x", padx=14)
        tk.Label(
            top,
            text=t("phone.ts_hint"),
            anchor=anchor,
            justify=justify,
            wraplength=545,
            fg="#37474f",
        ).pack(fill="x", padx=14)
        self.screen_label = tk.Label(
            top,
            text="",
            anchor=anchor,
            font=("TkDefaultFont", 11, "bold"),
            fg="#b71c1c",
        )
        self.screen_label.pack(fill="x", padx=14, pady=(6, 0))

        tk.Label(top, text=t("phone.token_label"), anchor=anchor).pack(
            fill="x", padx=14, pady=(10, 2)
        )
        self.token_var = tk.StringVar(value=server.token)
        token_entry = tk.Entry(
            top, textvariable=self.token_var, state="readonly", justify="left"
        )
        token_entry.pack(fill="x", padx=14)

        buttons = tk.Frame(top)
        buttons.pack(fill="x", padx=14, pady=(12, 4))
        self.stop_button = tk.Button(
            buttons, text=t("phone.stop"), width=13, command=self.stop_server
        )
        self.stop_button.pack(side="left")
        self.regen_button = tk.Button(
            buttons, text=t("phone.regen"), width=13, command=self.regenerate
        )
        self.regen_button.pack(side="left", padx=8)
        self.start_button = tk.Button(
            buttons,
            text=t("phone.start"),
            width=13,
            font=("TkDefaultFont", 10, "bold"),
            command=self.start_server,
        )
        self.start_button.pack(side="right")

        self.autostart_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            top,
            text=t("phone.autostart"),
            variable=self.autostart_var,
            command=self._save_autostart,
            anchor=anchor,
        ).pack(fill="x", padx=14, pady=(6, 2))
        # «يبدأ مع ويندوز» (ويندوز فقط): اختصار مجلد بدء التشغيل الذي
        # تديره وحدة autostart — الآلية نفسها التي ينشئها المثبّت.
        # الحالة الابتدائية من وجود ملف الاختصار فعلاً على القرص
        # لحظة فتح الحوار، لا من أي إعداد محفوظ.
        self.start_with_windows_var = tk.BooleanVar(
            value=autostart.is_startup_enabled()
        )
        self.start_with_windows_check = None
        if os.name == "nt":
            self.start_with_windows_check = tk.Checkbutton(
                top,
                text=t("start_with_windows"),
                variable=self.start_with_windows_var,
                command=self._toggle_start_with_windows,
                anchor=anchor,
            )
            self.start_with_windows_check.pack(fill="x", padx=14, pady=(2, 2))
        self.control_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            top,
            text=t("phone.control_toggle"),
            variable=self.control_var,
            command=self._save_control,
            anchor=anchor,
        ).pack(fill="x", padx=14, pady=(2, 2))
        self.tasks_button = tk.Button(
            top, text=t("phone.tasks_button"), command=self.open_tasks
        )
        self.tasks_button.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(
            top,
            text=t("phone.warning"),
            anchor=anchor,
            justify=justify,
            wraplength=545,
            fg="#b71c1c",
        ).pack(fill="x", padx=14, pady=(6, 0))

        top.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_status()
        self._load_autostart()
        self._load_control()
        self._refresh_screen_indicator()

    # -- عرض الحالة ---------------------------------------------------------
    def _refresh_status(self) -> None:
        if self.server.running:
            self.status_label.config(text=t("phone.status_running"))
            addresses = lan_ips()
            if addresses:
                # لاحقة ip_label هي " (Tailscale)" لعناوين Tailscale وفارغة لغيرها.
                lines = "\n".join(
                    f"http://{ip}:{self.server.port}" + ip_label(ip)[len(ip):]
                    for ip in addresses
                )
                self.address_label.config(text=t("phone.addresses", lines=lines))
            else:
                self.address_label.config(text=t("phone.no_address"))
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
        else:
            self.status_label.config(text=t("phone.status_stopped"))
            self.address_label.config(
                text=t("phone.port_when_started", port=self.server.port)
            )
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")

    # -- التحكّم ---------------------------------------------------------------
    def start_server(self) -> None:
        try:
            self.server.start()
        except Exception as exc:  # منفذ مشغول مثلاً — يُعرض ولا ينهار الحوار
            self.status_label.config(text=t("phone.err_start", error=exc))
            return
        self._refresh_status()

    def stop_server(self) -> None:
        self.server.stop()
        self._refresh_status()

    def regenerate(self) -> None:
        """رمز جديد: يُحفَظ في القاعدة ثم يسري على الخادم فوراً."""

        def job(engine):
            return regenerate_token(engine.db)

        def done(ok, value):
            if not ok:
                self.status_label.config(text=t("phone.err_regen", error=value))
                return
            self.server.set_token(value)
            self.token_var.set(value)
            self.status_label.config(text=t("phone.token_regenerated"))

        self.runner.submit(job, done)

    # -- التشغيل التلقائي -------------------------------------------------------
    def _load_autostart(self) -> None:
        def job(engine):
            return engine.db.get_setting(SETTING_AUTOSTART, "") == "1"

        def done(ok, value):
            if ok:
                self.autostart_var.set(bool(value))

        self.runner.submit(job, done)

    def _save_autostart(self) -> None:
        value = "1" if self.autostart_var.get() else ""

        def job(engine):
            engine.db.set_setting(SETTING_AUTOSTART, value)

        self.runner.submit(job)

    # -- يبدأ مع ويندوز (اختصار مجلد بدء التشغيل) ------------------------------
    def _toggle_start_with_windows(self) -> None:
        """ينشئ/يحذف اختصار بدء تشغيل ويندوز عبر وحدة autostart.

        الهدف ووسائطه من autostart.default_target() (والأيقونة من
        منطق الوحدة الافتراضي). عند أي فشل تعود خانة الاختيار إلى
        الحالة الحقيقية على القرص ويُعرَض الخطأ في تسمية حالة
        الحوار — آلية عرض أخطاء هذا الحوار نفسها.
        """
        new_value = bool(self.start_with_windows_var.get())
        try:
            target, args = autostart.default_target()
            autostart.set_startup_enabled(new_value, target=target, args=args)
        except Exception as exc:
            self.start_with_windows_var.set(autostart.is_startup_enabled())
            self.status_label.config(
                text=t("common.err_unexpected", error=exc)
            )

    # -- التحكم الكلي من الهاتف -------------------------------------------------
    def _load_control(self) -> None:
        def job(engine):
            return control_setting_enabled(
                engine.db.get_setting(SETTING_CONTROL_ENABLED, "true")
            )

        def done(ok, value):
            if ok:
                self.control_var.set(bool(value))

        self.runner.submit(job, done)

    def _save_control(self) -> None:
        # الكتابة بالقيمتين القانونيتين "true"/"false" اللتين يقرؤهما الخادم.
        value = "true" if self.control_var.get() else "false"

        def job(engine):
            engine.db.set_setting(SETTING_CONTROL_ENABLED, value)

        self.runner.submit(job)

    # -- مهام البوتات --------------------------------------------------------------
    def open_tasks(self) -> TasksWindow:
        return TasksWindow(self.top, self.runner, self.server)

    # -- مؤشّر مشاركة الشاشة ---------------------------------------------------------
    def _refresh_screen_indicator(self) -> None:
        """يُظهر «الشاشة مشتركة الآن» ما دام للخادم مشاهد بثّ حيّ.

        يتجدّد كل ثانيتين ما دامت النافذة مفتوحة؛ الإغلاق (من بروتوكول
        النافذة) يلغي التجدّد، وتدمير الويدجت من خارجه يوقفه بصمت.
        """
        try:
            if not self.top.winfo_exists():
                return
        except tk.TclError:
            return
        sharing = False
        try:
            sharing = (
                self.server is not None and self.server.screen_viewers > 0
            )
        except Exception:
            sharing = False
        self.screen_label.config(
            text=t("phone.screen_sharing") if sharing else ""
        )
        if self._closed:
            return
        try:
            self._screen_after = self.top.after(
                2000, self._refresh_screen_indicator
            )
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        self._closed = True
        if self._screen_after is not None:
            try:
                self.top.after_cancel(self._screen_after)
            except tk.TclError:
                pass
            self._screen_after = None
        try:
            self.top.destroy()
        except tk.TclError:
            pass


# ======================================================================
# النافذة الرئيسية
# ======================================================================
class KrouchiApp:
    """تطبيق المحادثة: قائمة بوتات جانبية ومحادثة المحدّد في الوسط."""

    def __init__(
        self,
        root: tk.Tk,
        runner: EngineRunner,
        bridge: _ApprovalBridge,
        server: CompanionServer | None = None,
    ):
        self.root = root
        self.runner = runner
        self.bridge = bridge
        self.server = server
        self.bots: list[dict] = []
        self.selected_bot_id: int | None = None
        self._history_token = 0
        self._working = False
        self._active_approval: ApprovalDialog | None = None
        self._active_item = None  # طلب السجلّ المعروض على البطاقة حالياً
        self._header_avatar_image = None  # مرجع صورة ترويسة البوت الحالي
        self.sidebar_frame: tk.Frame | None = None
        self.main_frame: tk.Frame | None = None

        # لغة الواجهة من إعدادات القاعدة (افتراضيها العربية) — تُقرأ قبل
        # بناء أي ويدجت، لأن كل النصوص والاتجاهات تُحسَب بلغة البناء.
        try:
            runner.call(lambda engine: i18n.load_lang(engine.db))
        except Exception:
            i18n.set_lang(i18n.DEFAULT_LANG)
        _set_window_icon(root)
        root.geometry("980x620")
        root.minsize(760, 480)
        self._build_layout()
        self.root.after(POLL_MS, self._poll_bridge)
        self.refresh_bots()

    # -- البناء ---------------------------------------------------------------
    def _build_layout(self) -> None:
        rtl = i18n.is_rtl()
        anchor = _text_anchor()
        self.root.title(t("app.title"))
        # الشريط الجانبي: على اليمين في العربية، على اليسار في الإنجليزية.
        sidebar = tk.Frame(self.root, width=250, relief="groove", borderwidth=1)
        sidebar.pack(side=_start_side(), fill="y")
        sidebar.pack_propagate(False)
        self.sidebar_frame = sidebar
        tk.Label(
            sidebar, text=t("app.bots"), anchor=anchor,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(fill="x", padx=8, pady=(8, 4))
        self.bots_list = tk.Listbox(sidebar, exportselection=False)
        self.bots_list.pack(fill="both", expand=True, padx=8)
        self.bots_list.bind("<<ListboxSelect>>", self._on_bot_selected)
        side_buttons = tk.Frame(sidebar)
        side_buttons.pack(fill="x", padx=8, pady=8)
        tk.Button(
            side_buttons, text=t("app.new_bot"), command=self.open_new_bot
        ).pack(fill="x", pady=2)
        tk.Button(
            side_buttons, text=t("app.edit_bot"), command=self.open_edit_bot
        ).pack(fill="x", pady=2)
        tk.Button(
            side_buttons, text=t("app.add_api"), command=self.open_add_api
        ).pack(fill="x", pady=2)
        tk.Button(
            side_buttons, text=t("app.shared_api"), command=self.open_shared_api
        ).pack(fill="x", pady=2)
        tk.Button(
            side_buttons, text=t("app.audit"), command=self.open_audit
        ).pack(fill="x", pady=2)
        tk.Button(
            side_buttons, text=t("app.phone_link"), command=self.open_phone_link
        ).pack(fill="x", pady=2)
        # منتقي اللغة: زرّ لكل لغة مكتوب باسمها الذاتي.
        lang_frame = tk.Frame(sidebar)
        lang_frame.pack(fill="x", padx=8, pady=(0, 8))
        tk.Label(lang_frame, text=t("app.language"), anchor=anchor).pack(fill="x")
        lang_buttons = tk.Frame(lang_frame)
        lang_buttons.pack(fill="x")
        self.lang_ar_button = tk.Button(
            lang_buttons,
            text=i18n.LANG_NAMES["ar"],
            command=lambda: self.switch_language("ar"),
        )
        self.lang_ar_button.pack(side="right", fill="x", expand=True, padx=(0, 2))
        self.lang_en_button = tk.Button(
            lang_buttons,
            text=i18n.LANG_NAMES["en"],
            command=lambda: self.switch_language("en"),
        )
        self.lang_en_button.pack(side="left", fill="x", expand=True, padx=(2, 0))
        self._mark_current_lang_button()

        # منطقة المحادثة.
        main = tk.Frame(self.root)
        main.pack(side=_end_side(), fill="both", expand=True)
        self.main_frame = main
        self.header_label = tk.Label(
            main, text=t("app.choose_bot"),
            anchor=anchor, font=("TkDefaultFont", 12, "bold"),
        )
        self.header_label.pack(fill="x", padx=10, pady=(8, 4))
        self.chat_text = tk.Text(main, wrap="word", state="disabled")
        self.chat_text.pack(fill="both", expand=True, padx=10)
        self._configure_chat_tags()
        status_frame = tk.Frame(main)
        status_frame.pack(fill="x", padx=10, pady=(4, 0))
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate")
        self.status_label = tk.Label(
            status_frame, text="", anchor=anchor, fg="#37474f"
        )
        self.status_label.pack(side=_start_side(), fill="x", expand=True)
        input_frame = tk.Frame(main)
        input_frame.pack(fill="x", padx=10, pady=8)
        self.send_button = tk.Button(
            input_frame, text=t("app.send"), width=10, command=self.send_current,
            font=("TkDefaultFont", 10, "bold"),
        )
        self.send_button.pack(side=_end_side())
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(input_frame, textvariable=self.entry_var)
        self.entry.pack(
            side=_start_side(), fill="x", expand=True,
            padx=(8, 0) if rtl else (0, 8),
        )
        self.entry.bind("<Return>", lambda _e: self.send_current())

    # -- تبديل اللغة --------------------------------------------------------------
    def _mark_current_lang_button(self) -> None:
        current = i18n.get_lang()
        for lang, button in (
            ("ar", self.lang_ar_button),
            ("en", self.lang_en_button),
        ):
            try:
                button.config(relief="sunken" if lang == current else "raised")
            except tk.TclError:
                pass

    def switch_language(self, lang: str) -> None:
        """يبدّل لغة الواجهة ويحفظها ويعيد بناء النافذة — بلا إعادة تشغيل.

        المحرّك وخادم المرافقة (إن كان يعمل) لا يُلمَسان إطلاقاً: إعادة
        البناء تستبدل إطاري النافذة الرئيسية فقط، وحلقة جسّ الموافقات
        مجدولة على الجذر نفسه فتستمر، والبوت المحدّد ومحادثته يعودان
        كما كانا.
        """
        if lang not in i18n.SUPPORTED_LANGS or lang == i18n.get_lang():
            return
        i18n.set_lang(lang)

        def job(engine):
            engine.db.set_setting(i18n.SETTING_KEY, lang)

        self.runner.submit(job)
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        # بطاقة موافقة معروضة: أوقف عدّادها وأغلقها دون حسم — طلبها يبقى
        # معلّقاً في السجلّ المشترك فتعيد حلقة الجسّ فتحه باللغة الجديدة.
        if self._active_approval is not None:
            self._active_approval._answered = True
            try:
                self._active_approval.top.destroy()
            except tk.TclError:
                pass
            self._active_approval = None
            self._active_item = None
        for frame in (self.sidebar_frame, self.main_frame):
            if frame is not None:
                try:
                    frame.destroy()
                except tk.TclError:
                    pass
        self._build_layout()
        self.refresh_bots(select_id=self.selected_bot_id)

    def _configure_chat_tags(self) -> None:
        justify = "right" if i18n.is_rtl() else "left"
        text = self.chat_text
        text.tag_configure("head_user", foreground="#1565c0",
                           font=("TkDefaultFont", 10, "bold"), justify=justify)
        text.tag_configure("body_user", justify=justify, spacing3=8)
        text.tag_configure("head_bot", foreground="#2e7d32",
                           font=("TkDefaultFont", 10, "bold"), justify=justify)
        text.tag_configure("body_bot", justify=justify, spacing3=8)
        text.tag_configure("note", foreground="#757575",
                           font=("TkDefaultFont", 9), justify=justify, spacing3=6)

    # -- جسّ سجلّ الموافقات المشترك ---------------------------------------------
    def _poll_bridge(self) -> None:
        # بطاقة معروضة حُسم طلبها من جهة أخرى (الهاتف مثلاً): أغلقها بقراره.
        if self._active_approval is not None and self._active_item is not None:
            if self._active_item.decision is not None:
                self._active_approval._finish(bool(self._active_item.decision))
        # لا بطاقة معروضة: اعرض أقدم طلب معلّق في السجلّ المشترك.
        if self._active_approval is None:
            pending = self.bridge.registry.pending()
            if pending:
                item = pending[0]

                def _answer(value, item=item):
                    self.bridge.registry.resolve(item.id, value, source="gui")
                    self._active_approval = None
                    self._active_item = None

                self._active_item = item
                self._active_approval = ApprovalDialog(
                    self.root, item.request, on_answer=_answer
                )
        try:
            self.root.after(POLL_MS, self._poll_bridge)
        except tk.TclError:
            pass

    # -- قائمة البوتات ------------------------------------------------------------
    def refresh_bots(self, select_id: int | None = None) -> None:
        def job(engine):
            return engine.db.list_bots(), engine.get_shared_api()

        def done(ok, value):
            if not ok:
                self.status_label.config(text=t("app.err_bots", error=value))
                return
            bots, shared = value
            self.bots = bots
            # شارة القائمة تقول الحقيقة تحت نموذج الواجهة المشتركة:
            # نموذجها، فاسم مزوّدها، فلا شيء.
            model = ""
            if shared is not None:
                model = shared[1] or shared[0]
            self.bots_list.delete(0, "end")
            for bot in bots:
                badge = mode_label(bot["approval_mode"])
                # Listbox نصّي لا يستضيف صوراً: التمثيل هنا أحادي
                # حرف الاسم دائماً (display_avatar_text) — القيمة
                # الخام المخزَّنة (إيموجي قديم/اسم ملف) لا تظهر.
                self.bots_list.insert(
                    "end",
                    f"{display_avatar_text(bot)} {bot['name']} · {model} · [{badge}]",
                )
            target = select_id if select_id is not None else self.selected_bot_id
            for index, bot in enumerate(bots):
                if bot["id"] == target:
                    self.bots_list.selection_set(index)
                    self._select_bot(bot["id"])
                    break
            else:
                if bots and self.selected_bot_id is None:
                    self.bots_list.selection_set(0)
                    self._select_bot(bots[0]["id"])

        self.runner.submit(job, done)

    def _on_bot_selected(self, _event=None) -> None:
        selection = self.bots_list.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.bots):
            self._select_bot(self.bots[index]["id"])

    def select_bot(self, bot_id: int) -> None:
        """اختيار برمجي (تستعمله الاختبارات وأزرار الواجهة)."""
        for index, bot in enumerate(self.bots):
            if bot["id"] == bot_id:
                self.bots_list.selection_clear(0, "end")
                self.bots_list.selection_set(index)
                break
        self._select_bot(bot_id)

    def _select_bot(self, bot_id: int) -> None:
        if bot_id == self.selected_bot_id:
            self._load_history(bot_id)
            return
        self.selected_bot_id = bot_id
        bot = next((b for b in self.bots if b["id"] == bot_id), None)
        if bot is not None:
            self.header_label.config(
                text=t(
                    "app.header_bot",
                    avatar=display_avatar_text(bot),
                    name=bot["name"],
                    provider=bot["provider_name"],
                    model=bot["model"] or t("app.default_model"),
                    mode=mode_label(bot["approval_mode"]),
                )
            )
            self._update_header_avatar_image(bot)
        self._load_history(bot_id)

    def _update_header_avatar_image(self, bot: dict) -> None:
        """صورة المعرض بجانب نصّ الترويسة إن وُجدت، وإلا بلا صورة.

        الترويسة Label فيستطيع استضافة صورة رخيصاً (على خلاف قائمة
        Listbox): قيمة معرضية + ملف موجود ⇒ صورة مصغّرة مرافقة
        للنصّ (compound)؛ غير ذلك — قيمة قديمة/فارغة أو ملف غائب —
        يُمسح أي صورة سابقة ويبقى نصّ الأحادي وحده، بلا انهيار.
        """
        self._header_avatar_image = None
        try:
            path = avatar_image_path(bot.get("avatar"))
            image = (
                _load_avatar_thumbnail(path, size=32)
                if path is not None
                else None
            )
            if image is not None:
                self._header_avatar_image = image
                self.header_label.config(
                    image=image,
                    compound="right" if i18n.is_rtl() else "left",
                )
            else:
                self.header_label.config(image="", compound="none")
        except tk.TclError:
            pass

    # -- عرض المحادثة ---------------------------------------------------------------
    def _load_history(self, bot_id: int) -> None:
        self._history_token += 1
        token = self._history_token

        def job(engine):
            return engine.db.get_bot(bot_id), engine.history(bot_id)

        def done(ok, value):
            if not ok or token != self._history_token:
                return
            bot, rows = value
            if bot is not None:
                self._render_history(bot, rows)

        self.runner.submit(job, done)

    def _chat_insert(self, text: str, tag: str) -> None:
        self.chat_text.insert("end", text + "\n", tag)

    def _render_history(self, bot: dict, rows: list[dict]) -> None:
        widget = self.chat_text
        widget.config(state="normal")
        widget.delete("1.0", "end")
        for row in rows:
            role = row["role"]
            content = row["content"] or ""
            if role == "user":
                self._chat_insert(t("app.you"), "head_user")
                if content:
                    self._chat_insert(content, "body_user")
            elif role == "assistant":
                if content:
                    # رأس الرسالة داخل Text: أحادي الحرف نصّاً فقط
                    # (تضمين صورة في متن المحادثة ليس رخيصاً هنا).
                    self._chat_insert(
                        f"{display_avatar_text(bot)} {bot['name']}", "head_bot"
                    )
                    self._chat_insert(content, "body_bot")
                if row.get("tool_calls_json"):
                    try:
                        calls = json.loads(row["tool_calls_json"])
                        names = [
                            action_label(
                                c.get("function", {}).get("name", "?")
                            )
                            for c in calls
                        ]
                        self._chat_insert(
                            t(
                                "app.bot_requested",
                                names=t("app.list_sep").join(names),
                            ),
                            "note",
                        )
                    except (ValueError, AttributeError):
                        pass
            elif role == "tool":
                short = content if len(content) <= 200 else content[:200] + "…"
                self._chat_insert(t("app.tool_result", text=short), "note")
        widget.config(state="disabled")
        widget.see("end")

    def _append_local(self, head: str, body: str, head_tag: str, body_tag: str) -> None:
        widget = self.chat_text
        widget.config(state="normal")
        self._chat_insert(head, head_tag)
        if body:
            self._chat_insert(body, body_tag)
        widget.config(state="disabled")
        widget.see("end")

    # -- الإرسال -----------------------------------------------------------------------
    def _set_working(self, working: bool) -> None:
        self._working = working
        self.send_button.config(state="disabled" if working else "normal")
        if working:
            self.status_label.config(text=t("app.working"))
            self.progress.pack(side=_end_side(), padx=(0, 8))
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.status_label.config(text="")

    def send_current(self) -> None:
        text = self.entry_var.get().strip()
        if not text or self._working:
            return
        if self.selected_bot_id is None:
            self.status_label.config(text=t("app.need_bot"))
            return
        bot_id = self.selected_bot_id
        bot = next((b for b in self.bots if b["id"] == bot_id), None)
        self.entry_var.set("")
        if bot is not None:
            self._append_local(t("app.you"), text, "head_user", "body_user")
        self._set_working(True)

        def job(engine):
            return engine.send_message(bot_id, text)

        def done(ok, value):
            self._set_working(False)
            if not ok:
                self.status_label.config(text=t("app.err_generic", error=value))
            self._load_history(bot_id)

        self.runner.submit(job, done)

    # -- النوافذ الفرعية ------------------------------------------------------------------
    def open_new_bot(self) -> None:
        BotDialog(self.root, self.runner, on_saved=lambda: self.refresh_bots())

    def open_edit_bot(self) -> None:
        bot = next(
            (b for b in self.bots if b["id"] == self.selected_bot_id), None
        )
        if bot is None:
            self.status_label.config(text=t("app.need_bot_edit"))
            return
        BotDialog(
            self.root,
            self.runner,
            bot=bot,
            on_saved=lambda: self.refresh_bots(select_id=bot["id"]),
        )

    def open_add_api(self) -> None:
        AddApiDialog(self.root, self.runner)

    def open_shared_api(self) -> None:
        SharedApiDialog(
            self.root,
            self.runner,
            on_saved=lambda: self.refresh_bots(select_id=self.selected_bot_id),
        )

    def open_audit(self) -> None:
        AuditWindow(self.root, self.runner)

    def open_phone_link(self) -> None:
        if self.server is None:
            self.status_label.config(text=t("app.no_server"))
            return
        PhoneLinkDialog(self.root, self.runner, self.server)

    def on_close(self) -> None:
        if self.server is not None:
            try:
                self.server.stop()
            except Exception:
                pass
        self.runner.shutdown()
        self.root.destroy()


# ======================================================================
# نقطة الدخول
# ======================================================================
def _setup_fonts(root: tk.Tk) -> None:
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(size=11)
        except tk.TclError:
            pass


def _make_companion_server(
    runner: EngineRunner, bridge: _ApprovalBridge
) -> CompanionServer:
    """يهيّئ خادم مرافقة الهاتف من إعدادات قاعدة البيانات.

    رمز الربط يُولَّد ويُحفَظ عند أول مرة؛ المنفذ والتشغيل التلقائي من
    الإعدادات نفسها (الافتراضي: منفذ 8765، وبلا تشغيل تلقائي). فشل
    الربط عند التشغيل التلقائي لا يمنع فتح التطبيق — تبقى حالة الخادم
    ظاهرة وقابلة للإصلاح من نافذة «ربط الهاتف».
    """

    def job(engine):
        token = get_or_create_token(engine.db)
        raw_port = engine.db.get_setting(SETTING_PORT, "")
        try:
            port = int(raw_port) if raw_port else SERVER_DEFAULT_PORT
        except ValueError:
            port = SERVER_DEFAULT_PORT
        autostart = engine.db.get_setting(SETTING_AUTOSTART, "") == "1"
        return token, port, autostart

    token, port, autostart = runner.call(job)
    server = CompanionServer(
        engine_call=runner.call_blocking,
        registry=bridge.registry,
        token=token,
        port=port,
    )
    if autostart:
        try:
            server.start()
        except Exception:
            pass  # يبقى متوقّفاً؛ حالته تظهر في نافذة ربط الهاتف
    return server


def main(data_dir: str | Path | None = None) -> None:
    """يفتح التطبيق على مجلد البيانات (الافتراضي ~/.krouchi_dz)."""
    root = tk.Tk()
    _setup_fonts(root)
    bridge = _ApprovalBridge()
    target_dir = Path(data_dir) if data_dir else default_data_dir()

    def factory() -> ChatEngine:
        return ChatEngine(
            target_dir,
            approval_registry=bridge.registry,
            ask_timeout=ASK_TIMEOUT,
        )

    runner = EngineRunner(factory)
    try:
        runner.wait_ready()
    except Exception as exc:
        root.withdraw()
        messagebox.showerror(
            "Krouchi_DZ", t("err.engine_start_failed", error=exc)
        )
        root.destroy()
        raise
    runner.attach(root)
    server = _make_companion_server(runner, bridge)
    app = KrouchiApp(root, runner, bridge, server=server)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
