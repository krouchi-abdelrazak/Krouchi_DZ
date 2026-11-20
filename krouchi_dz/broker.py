"""وسيط الموافقات (Approval Broker) — قلب Krouchi_DZ.

كل إجراء يطلبه بوت (قراءة ملف، كتابة ملف، تشغيل أمر) يمرّ من هنا قبل
التنفيذ، بحسب نمط البوت:

- ask      : النمط الافتراضي والأكثر أماناً — يُسأل المستخدم. لا وسيلة
             سؤال، أو خطأ فيها، أو انتهاء المهلة دون جواب = رفض
             (فشل مُغلق Fail-Closed).
- full     : سماح كامل دون سؤال — تفعيل صريح لكل بوت على حدة.
- readonly : القراءة مسموحة؛ الكتابة والأوامر مرفوضة دائماً.

سؤال المستخدم في نمط ask يمرّ بإحدى قناتين:
- ردّ نداء (ask_callback) يقدّمه المضيف، أو
- سجلّ الموافقات المعلّقة المشترك (PendingApprovals) إن مُرّر للوسيط:
  الوسيط يسجّل الطلب في السجلّ وينتظر حسمه، وأيّ واجهة تصل إلى السجلّ
  (بطاقة الواجهة الرسومية على الحاسوب، أو خادم مرافقة الهاتف) تستطيع
  حسمه — فالقرار واحد مهما كانت جهته، وانتهاء المهلة دون حسم = رفض
  ويُسحَب الطلب من السجلّ.

كل قرار (سماح أو رفض وسببه) يُسجَّل عبر ردّ نداء التدقيق (audit)
الذي يربطه المحرّك بجدول audit_log في قاعدة البيانات.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

ACTIONS = (
    "read_file", "read_document", "read_clipboard", "see_screen",
    "write_file", "run_command", "open_target", "power",
    "print_file", "upload_file", "set_clipboard",
    "window_control", "kill_process", "clear_conversation",
    "type_text", "press_keys",
    "use_skill", "save_skill", "remember",
)
READONLY_ALLOWED = (
    "read_file", "read_document", "read_clipboard", "see_screen",
    "use_skill",
)

# أسباب القرارات (تُحفظ في سجلّ التدقيق وتظهر للمستخدم).
REASON_FULL = "وضع الوصول الكامل"
REASON_READONLY_OK = "وضع القراءة فقط — قراءة مسموحة"
REASON_READONLY_DENY = "وضع القراءة فقط — الإجراء ممنوع"
REASON_APPROVED = "وافق المستخدم"
REASON_DENIED = "رفض المستخدم"
REASON_NO_CALLBACK = "لا وسيلة لسؤال المستخدم — رفض تلقائي"
REASON_TIMEOUT = "انتهت مهلة الإجابة — رفض تلقائي"
REASON_CALLBACK_ERROR = "خطأ في وسيلة السؤال — رفض تلقائي"
REASON_UNKNOWN_ACTION = "إجراء غير معروف"


@dataclass
class ApprovalRequest:
    """طلب موافقة واحد يُعرض على المستخدم."""

    bot_id: int | None
    bot_name: str
    action: str
    params: dict = field(default_factory=dict)
    mode: str = "ask"
    # سياق اختياري: معرّف المهمة (tasks) التي ينتمي إليها الطلب، إن وُجدت —
    # يظهر في ملخّص المعلّق لتعرف الواجهات صاحب الطلب وتُظهر المهمة
    # بحالة «بانتظار الموافقة». None لطلبات المحادثة والتحكّم المباشر.
    task_id: int | None = None


def request_summary(request: "ApprovalRequest") -> str:
    """نصّ هدف الإجراء كما يُعرض على المستخدم (مسار/أمر + معاينة كتابة).

    مصدر واحد للنصّ: تستعمله بطاقة الموافقة في الواجهة الرسومية
    وخادم الهاتف في ملخّصات /api/approvals على حدّ سواء.
    """
    params = request.params or {}
    if request.action in ("read_file", "read_document", "write_file"):
        text = str(params.get("path", "؟"))
        if request.action == "write_file":
            content = str(params.get("content", ""))
            preview = content if len(content) <= 300 else content[:300] + "…"
            text += f"\n\nالمحتوى ({len(content)} حرفاً):\n{preview}"
        return text
    if request.action == "read_clipboard":
        return "قراءة نصّ الحافظة الحالية على الجهاز"
    if request.action == "see_screen":
        question = str(params.get("question", "") or "").strip()
        summary = "رؤية شاشة الحاسوب الحالية والتقاط صورتها"
        if question:
            summary += f" — السؤال: {question}"
        return summary
    if request.action == "run_command":
        return str(params.get("command", "؟"))
    if request.action == "open_target":
        return str(params.get("target", "؟"))
    if request.action == "power":
        labels = {
            "shutdown": "إيقاف الحاسوب",
            "restart": "إعادة تشغيل الحاسوب",
            "lock": "قفل الحاسوب",
            "sleep": "وضع الحاسوب في السكون",
            "logoff": "تسجيل الخروج من الحاسوب",
        }
        return labels.get(str(params.get("action", "")), "فعل طاقة")
    if request.action == "print_file":
        text = str(params.get("path", "؟"))
        if params.get("printer"):
            text += f"\nالطابعة: {params['printer']}"
        return text
    if request.action == "upload_file":
        return f"{params.get('path', '؟')} ({params.get('size', 0)} بايت)"
    if request.action == "set_clipboard":
        content = str(params.get("text", ""))
        preview = content if len(content) <= 300 else content[:300] + "…"
        return preview
    if request.action == "window_control":
        return f"نافذة {params.get('id', '؟')}: {params.get('action', '؟')}"
    if request.action == "kill_process":
        return f"إنهاء العملية {params.get('pid', '؟')}"
    if request.action == "clear_conversation":
        return "مسح كامل محادثة هذا البوت مع المستخدم نهائياً"
    if request.action == "type_text":
        content = str(params.get("text", ""))
        preview = content if len(content) <= 300 else content[:300] + "…"
        return f"كتابة نص في النافذة المركّزة ({len(content)} حرفاً):\n{preview}"
    if request.action == "press_keys":
        return f"ضغط مفاتيح: {params.get('keys', '؟')}"
    if request.action == "use_skill":
        return f"قراءة تعليمات المهارة: {params.get('name', '؟')}"
    if request.action == "save_skill":
        text = f"حفظ مهارة: {params.get('name', '؟')}"
        description = str(params.get("description", "") or "").strip()
        if description:
            text += f" — {description}"
        instructions = str(params.get("instructions", ""))
        preview = (
            instructions
            if len(instructions) <= 300
            else instructions[:300] + "…"
        )
        text += f"\n\nالتعليمات ({len(instructions)} حرفاً):\n{preview}"
        return text
    if request.action == "remember":
        return f"حفظ في الذاكرة: {params.get('fact', '؟')}"
    return json.dumps(params, ensure_ascii=False)


@dataclass
class BrokerDecision:
    allowed: bool
    reason: str


@dataclass
class PendingApproval:
    """طلب موافقة معلّق في السجلّ المشترك بانتظار حسمه من أي واجهة."""

    id: str
    request: ApprovalRequest
    created_at: str  # وقت الإنشاء ISO — يُعرض في /api/approvals
    created_mono: float  # monotonic — لحساب النوافذ الزمنية بدقة
    event: threading.Event = field(default_factory=threading.Event, repr=False)
    decision: bool | None = None  # None ما دام معلّقاً
    resolved_by: str = ""  # "gui" | "phone" | "timeout" | "callback" | …
    resolved_mono: float = 0.0


class PendingApprovals:
    """سجلّ طلبات الموافقة المعلّقة — نقطة الالتقاء الوحيدة بين الواجهات.

    الوسيط (أو ردّ نداء الجسر) يسجّل الطلب هنا وينتظر حدثه؛ الواجهة
    الرسومية وخادم الهاتف يقرآن المعلّق ويحسمانه. كل العمليات محروسة
    بقفل واحد، والحسم يحدث مرة واحدة فقط (الأول يفوز)، وانتهاء مهلة
    الوسيط يسحب الطلب عبر expire() فيُحسَم رفضاً بمصدر «timeout».
    يحتفظ السجلّ بآخر القرارات المحسومة (بحدّ أقصى) لتستعلم عنها
    واجهة المحادثة (هل رُفض شيء أثناء هذه الرسالة؟).
    """

    MAX_RESOLVED_KEPT = 200

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: dict[str, PendingApproval] = {}
        self._resolved: list[PendingApproval] = []

    def create(self, request: ApprovalRequest) -> PendingApproval:
        """يسجّل طلباً معلّقاً جديداً ويعيده (حدثه غير مُشعَل)."""
        item = PendingApproval(
            id=uuid.uuid4().hex[:16],
            request=request,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_mono=time.monotonic(),
        )
        with self._lock:
            self._pending[item.id] = item
        return item

    def pending(self) -> list[PendingApproval]:
        """الطلبات المعلّقة الآن، الأقدم أولاً."""
        with self._lock:
            return list(self._pending.values())

    def get(self, item_id: str) -> PendingApproval | None:
        with self._lock:
            return self._pending.get(item_id)

    def resolve(self, item_id: str, approved: bool, source: str = "") -> bool:
        """يحسم طلباً معلّقاً ويوقظ منتظره. False إن لم يوجد أو حُسم قبلاً."""
        with self._lock:
            item = self._pending.pop(item_id, None)
            if item is None:
                return False
            item.decision = bool(approved)
            item.resolved_by = source
            item.resolved_mono = time.monotonic()
            self._resolved.append(item)
            del self._resolved[: -self.MAX_RESOLVED_KEPT]
            item.event.set()
            return True

    def expire(self, item_id: str) -> bool:
        """يُنهي طلباً انتهت مهلته: قراره رفض ومصدره المهلة."""
        return self.resolve(item_id, False, source="timeout")

    def resolved_since(
        self, since_mono: float, bot_id: int | None = None
    ) -> list[PendingApproval]:
        """الطلبات التي حُسمت منذ لحظة monotonic معيّنة (لبوت محدّد إن طُلب)."""
        with self._lock:
            items = [i for i in self._resolved if i.resolved_mono >= since_mono]
        if bot_id is not None:
            items = [i for i in items if i.request.bot_id == bot_id]
        return items


class ApprovalBroker:
    """يقرّر السماح أو الرفض لكل إجراء، ويُدقّق كل قرار."""

    def __init__(
        self,
        ask_callback=None,
        ask_timeout: float = 60.0,
        audit=None,
        registry: PendingApprovals | None = None,
    ):
        # ask_callback: دالة تأخذ ApprovalRequest وتعيد True/False.
        # audit: دالة (bot_id, action, decision, reason, details).
        # registry: سجلّ الموافقات المعلّقة المشترك — إن مُرّر يُستعمَل
        # لسؤال المستخدم بدل ردّ النداء (تحسمه أي واجهة تصل إلى السجلّ).
        self.ask_callback = ask_callback
        self.ask_timeout = float(ask_timeout)
        self.audit = audit
        self.registry = registry

    # -- داخلي ---------------------------------------------------------
    def _log(self, request: ApprovalRequest, decision: BrokerDecision) -> None:
        if self.audit is not None:
            self.audit(
                request.bot_id,
                request.action,
                "allowed" if decision.allowed else "denied",
                decision.reason,
                {"params": request.params, "mode": request.mode},
            )

    def _ask_via_registry(self, request: ApprovalRequest) -> BrokerDecision:
        """يسأل عبر السجلّ المشترك: تسجيل وانتظار حسم أي واجهة.

        انتهاء المهلة دون حسم = رفض، ويُسحَب الطلب من السجلّ حتى لا
        يبقى معروضاً على الواجهات بعد فوات أوانه.
        """
        item = self.registry.create(request)
        if item.event.wait(self.ask_timeout):
            if item.decision:
                return BrokerDecision(True, REASON_APPROVED)
            return BrokerDecision(False, REASON_DENIED)
        self.registry.expire(item.id)
        return BrokerDecision(False, REASON_TIMEOUT)

    def _ask_user(self, request: ApprovalRequest) -> BrokerDecision:
        """يسأل المستخدم مع مهلة؛ أي غياب للجواب = رفض (فشل مُغلق)."""
        if self.registry is not None:
            return self._ask_via_registry(request)
        if self.ask_callback is None:
            return BrokerDecision(False, REASON_NO_CALLBACK)
        outcome: dict = {}

        def _run() -> None:
            try:
                outcome["value"] = self.ask_callback(request)
            except Exception:
                outcome["error"] = True

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(self.ask_timeout)
        if worker.is_alive():
            return BrokerDecision(False, REASON_TIMEOUT)
        if outcome.get("error"):
            return BrokerDecision(False, REASON_CALLBACK_ERROR)
        if outcome.get("value"):
            return BrokerDecision(True, REASON_APPROVED)
        return BrokerDecision(False, REASON_DENIED)

    # -- واجهة عامة ------------------------------------------------------
    def authorize(
        self,
        bot: dict,
        action: str,
        params: dict | None = None,
        *,
        force_ask: bool = False,
        task_id: int | None = None,
    ) -> BrokerDecision:
        """يقرّر بشأن إجراء لبوت معيّن ويسجّل القرار في التدقيق.

        force_ask: يتجاوز اختصارات الأنماط (full/readonly) ويسأل
        المستخدم دائماً — لأفعال التحكّم الخطرة (كالطاقة) التي لا
        يكفي فيها نمط البوت وحده. task_id: سياق المهمة المالكة
        للطلب إن وُجدت، يُحمل إلى السجلّ المشترك.
        """
        params = params or {}
        mode = (bot or {}).get("approval_mode", "ask")
        request = ApprovalRequest(
            bot_id=(bot or {}).get("id"),
            bot_name=(bot or {}).get("name", "؟"),
            action=action,
            params=params,
            mode=mode,
            task_id=task_id,
        )
        if action not in ACTIONS:
            decision = BrokerDecision(False, REASON_UNKNOWN_ACTION)
        elif force_ask:
            decision = self._ask_user(request)
        elif mode == "full":
            decision = BrokerDecision(True, REASON_FULL)
        elif mode == "readonly":
            if action in READONLY_ALLOWED:
                decision = BrokerDecision(True, REASON_READONLY_OK)
            else:
                decision = BrokerDecision(False, REASON_READONLY_DENY)
        else:  # ask — الافتراضي
            decision = self._ask_user(request)
        self._log(request, decision)
        return decision
