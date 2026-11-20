"""محرّك المحادثة في Krouchi_DZ — مستقل عن أي واجهة (تقوده واجهة الخطوة 2).

يربط: قاعدة البيانات المحلية، ملف إعدادات المزوّدين، مخزن الأسرار،
ووسيط الموافقات. إرسال رسالة لبوت يحفظ الذاكرة لكل بوت في SQLite،
وإذا طلب النموذج أدوات (read_file / read_document / read_clipboard /
write_file / run_command / open_target / window_action / type_text /
press_keys) نُفّذت عبر الوسيط فقط، وأُعيدت نتائجها للنموذج ليكمل
ردّه. وحدها list_windows قراءة محضة فتُنفَّذ بلا وسيط. أداتا الكتابة
(type_text / press_keys) تقودان مصرف إدخال remote نفسه الذي يستعمله
مسار إدخال الهاتف (/api/input)، وأداتا القراءة الجديدتان: read_document
تستخرج نصّ وثيقة (docx حقيقي بالمكتبة القياسية، أو ملف نصّي بترميزه
الصحيح)، وread_clipboard تقرأ الحافظة بقارئ طبقة التحكّم نفسه
(control.get_clipboard) الذي يقف خلف GET /api/clipboard.

وأداة see_screen (الإصدار 3.5.0 «العينان») تمنح البوت عينين: تلتقط
الشاشة بمسار الالتقاط المثبت نفسه خلف /api/screen/frame (مصدر شاشة
remote: grab_jpeg) وتُسلّم الصورة للنموذج جزءَ صورة حقيقياً في
المحادثة؛ فإن رفضها المزوّد (نموذج نصّي) تدهورَت الأداة بأمان إلى
نصّ إرشادي عربي واضح — لا انهيار ولا ردّ فارغ صامت.

والإصدار 3.6.0 «التعلّم والمهارات»: البوتات تتعلّم وتكسب مهارات
وتحفظها في ذاكرتها الدائمة — مهارات (skills) بفهرس يُحقن في موجّه
النظام تُقرأ كاملة بـ use_skill وتُحفظ بـ save_skill، وملاحظات
ذاكرة (bot_memory) تُحفظ بـ remember وتُحقن أحدثها في كل محادثة.
واستخراج نصوص الوثائق انتقل إلى documents.extract_text — قارئ عام
واحد (docx/xlsx/pdf/نصّية) تستعمله read_document ومرفقات المحادثة
(prepare_attachment: زرّ + في الواجهات) على حدّ سواء.

ونقطة الدخول الأولى لإدخال API هي add_api(base_url, api_key):
أي عنوان + أي مفتاح، فيسجّل المزوّد ويكتشف نماذجه بنفسه (discovery.py).
"""

from __future__ import annotations

import base64
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import control, i18n, remote
from .broker import ApprovalBroker
from .config import ProviderConfig, load_providers, save_providers
from .db import Database
from .discovery import (
    ERR_NO_KEY,
    MODELS_CACHE_TTL,
    DiscoveryError,
    DiscoveryResult,
    classify_kind,
    derive_name,
    discover_models,
    normalize_base_url,
    sanitize_name,
)
from .documents import DOC_TEXT_EXTS, extract_text
from .providers import TOOLS, ChatResult, ProviderError, ToolCall, build_provider
from .secrets import SecretsStore

MAX_TOOL_ROUNDS = 5          # حدّ جولات الأدوات في الرسالة الواحدة
MAX_FILE_CHARS = 200_000     # حدّ حجم القراءة المعادة للنموذج
MAX_DOC_CHARS = 12_000       # حدّ نصّ الوثيقة/الحافظة المعاد للنموذج
COMMAND_TIMEOUT = 30.0       # مهلة تنفيذ أمر واحد (ثوانٍ)
TEXT_EVENT_MAX = 2000        # حدّ طول حدث «text» واحد في remote.validate_input_event
SCREEN_IMAGE_MAX_WIDTH = 1024  # أقصى عرض لصورة see_screen المرسلة للنموذج
SCREEN_IMAGE_QUALITY = 70      # جودة JPEG لصورة see_screen

# نصّ التدهور الآمن لأداة see_screen: يصل النموذج نتيجةً للأداة حين
# يكون نموذج Krouchi AI الحالي نصّياً لا يرى الصور — فيخبر المستخدم
# بوضوح بدل أن ينهار أو يردّ فارغاً.
VISION_UNSUPPORTED_TEXT = (
    "تعذّرت رؤية الشاشة: نموذج Krouchi AI الحالي نموذج نصّي لا يرى "
    "الصور. أخبر المستخدم بذلك بوضوح، واطلب منه اختيار نموذج بصري "
    "(يدعم الصور) في «Krouchi AI» — الذكاء المشترك لكل البوتات — "
    "ثم إعادة المحاولة. وحتى ذلك الحين اعتمد على عينيك الأخريين: "
    "read_document لقراءة الوثائق، وread_clipboard لقراءة الحافظة، "
    "وlist_windows لمعرفة النوافذ المفتوحة."
)

# كلمات مفتاحية في متن خطأ المزوّد تدلّ على رفض الصورة لكون النموذج
# نصّياً (تُقرأ مع «400» في نصّ ProviderError: «HTTP 400 من المزوّد: …»).
_VISION_REJECT_HINTS = (
    "image", "vision", "multimodal", "image_url", "inline_data",
    "modalit", "صورة", "صور", "بصر",
)


def _is_vision_rejection(exc: Exception) -> bool:
    """هل خطأ المزوّد رفضٌ لصورة أُرسلت لنموذج نصّي؟

    الرفض الحقيقي من نقاط OpenAI المتوافقة يأتي HTTP 400 ومتنه يذكر
    الصورة/الرؤية (image/vision/multimodal…)؛ أي خطأ آخر (شبكة،
    مصادقة، حدّ معدّل) ليس رفض رؤية فلا يُتدهوَر بل يصعد كما هو.
    """
    text = str(exc)
    if "400" not in text:
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in _VISION_REJECT_HINTS)

# امتدادات الملفات النصّية وصيغ الوثائق كلها في documents.py —
# القارئ العام الواحد (extract_text)؛ يُعاد تصدير الاسم هنا توافقاً.
# DOC_TEXT_EXTS مستورَدة في أعلى الوحدة من .documents.

# نصّ التدهور الآمن لصورة مرفقة في المحادثة (زرّ +): يصل النموذج
# بدل الصورة حين يكون نموذج Krouchi AI الحالي نصّياً لا يرى الصور.
ATTACH_VISION_UNSUPPORTED_TEXT = (
    "ملاحظة: أُرفقت صورة بهذه الرسالة، لكن نموذج Krouchi AI "
    "الحالي نموذج نصّي لا يرى الصور فلم تصل إليه الصورة. أخبر "
    "المستخدم بذلك بوضوح، واطلب منه اختيار نموذج بصري (يدعم "
    "الصور) في «Krouchi AI» ثم إعادة إرسال الصورة."
)

# أنواع MIME للصور التي يقبلها زرّ الإرفاق (امتداد ← نوع).
ATTACH_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
ATTACH_MAX_BYTES = 25 * 1024 * 1024  # حدّ حجم الملف المرفق الواحد


def _truncate_doc_text(text: str) -> str:
    """يقطع نصّ وثيقة/مرفق عند حدّ MAX_DOC_CHARS مع ملاحظة استمرار."""
    if len(text) > MAX_DOC_CHARS:
        return text[:MAX_DOC_CHARS] + (
            f"\n…[قُطعت القراءة عند {MAX_DOC_CHARS} حرف: "
            "الوثيقة أطول من ذلك ونصّها يستمرّ بعد هذا الموضع]"
        )
    return text


def prepare_attachment(path) -> dict:
    """يهيّئ ملفاً واحداً مرفقاً في محادثة (زرّ + في الواجهات).

    صورة (png/jpg/jpeg/webp/gif) ⇒ {"kind": "image", "name",
    "data_uri"} جاهزة كجزء صورة للنموذج؛ وأي ملف آخر يمرّ بالقارئ
    العام documents.extract_text ⇒ {"kind": "text", "name",
    "text"} مقطوعاً عند حدّ الوثائق. الأخطاء ValueError عربية
    واضحة (غير موجود/أكبر من الحدّ/تالف/غير مدعوم) — بلا انهيار.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"الملف غير موجود: {file_path}")
    if file_path.stat().st_size > ATTACH_MAX_BYTES:
        raise ValueError("الملف المرفق أكبر من الحدّ (25 ميغابايت)")
    ext = file_path.suffix.lower()
    if ext in ATTACH_IMAGE_MIME:
        data_uri = (
            f"data:{ATTACH_IMAGE_MIME[ext]};base64,"
            + base64.b64encode(file_path.read_bytes()).decode("ascii")
        )
        return {"kind": "image", "name": file_path.name, "data_uri": data_uri}
    text = extract_text(file_path.read_bytes(), file_path.name)
    if not text.strip():
        text = "الملف لا يحوي نصاً قابلاً للقراءة"
    return {
        "kind": "text",
        "name": file_path.name,
        "text": _truncate_doc_text(text),
    }

# -- الواجهة المشتركة: API واحدة لكل البوتات، تُدخَل مرة واحدة ------------
SETTING_SHARED_PROVIDER = "shared_provider"
SETTING_SHARED_MODEL = "shared_model"

# -- توجيه البوت المدمج -----------------------------------------------------
# أسماء الأدوات الحقيقية كما في providers.TOOLS حرفياً (منها see_screen
# منذ 3.5.0: عينا البوت على الشاشة بمسار التقاط remote نفسه).
_TOOL_NAMES_AR = "، ".join(t["function"]["name"] for t in TOOLS)
_TOOL_NAMES_EN = ", ".join(t["function"]["name"] for t in TOOLS)

ORIENTATION_AR = (
    "أنت بوت حاسوب داخل تطبيق Krouchi_DZ، تعمل على حاسوب المدير "
    f"(المستخدم) وتنفّذ أوامره بأدواتك: {_TOOL_NAMES_AR}. "
    "الأفعال الكبيرة تمرّ بموافقة المدير عبر وسيط الموافقات؛ نفّذ ما "
    "يوافق عليه فقط، واذكر باختصار ما فعلته وما تعذّر عليك. "
    "وللكتابة داخل أي برنامج (كـ Word): افتحه بـ open_target، ركّز "
    "نافذته بـ list_windows ثم window_action (focus)، اكتب المحتوى "
    "بـ type_text، وتنقّل بين الحقول بـ press_keys (tab/enter)، "
    "واحفظ في النهاية بـ press_keys (ctrl+s). "
    "وللقراءة: اقرأ وثيقة (كرسالة رسمية .docx) بـ read_document "
    "ونصّ الحافظة بـ read_clipboard، ثم لخّصها للمدير أو اكتب الردّ "
    "عليها بسير الكتابة أعلاه. "
    "ولك عينان أيضاً: انظر إلى الشاشة بـ see_screen قبل التصرّف "
    "كلما لم تكن متأكّداً مما هو مفتوح أو معروض الآن، وصِف باختصار "
    "ما رأيته، ثم تصرّف بيديك بناءً على ما رأيت. "
    "وأنت تتعلّم وتتذكّر: مهاراتك المحفوظة وذاكرتك تظهران في بداية "
    "كل محادثة — فقبل أي مهمة مألوفة اقرأ مهارة الموضوع بـ "
    "use_skill واتّبع تعليماتها، وحين يعلّمك المدير إجراءً أو صيغة "
    "عمل احفظها بـ save_skill، وحين تعرف حقيقة دائمة عن عمله "
    "احفظها بـ remember، ولا تحفظ سراً ولا كلمة مرور أبداً."
)
ORIENTATION_EN = (
    "You are a computer bot inside the Krouchi_DZ app, running on the "
    "director's (the user's) computer, carrying out his orders with "
    f"your tools: {_TOOL_NAMES_EN}. Major actions pass through the "
    "director's approval broker; only do what gets approved, and "
    "briefly state what you did and what you could not do. "
    "To write inside any program (e.g. Word): open it with "
    "open_target, focus its window via list_windows then "
    "window_action (focus), type the content with type_text, move "
    "between fields with press_keys (tab/enter), and save at the "
    "end with press_keys (ctrl+s). "
    "To read: read a document (e.g. an official letter .docx) with "
    "read_document and the clipboard text with read_clipboard, then "
    "summarize it for the director or type the reply using the "
    "writing workflow above. "
    "You also have eyes: look at the screen with see_screen before "
    "acting whenever you are unsure what is open or shown right "
    "now, briefly describe what you saw, then act with your hands "
    "based on what you saw. "
    "And you learn and remember: your saved skills and your memory "
    "appear at the start of every conversation — before a familiar "
    "task, read the matching skill with use_skill and follow its "
    "instructions; when the director teaches you a procedure or a "
    "work format, save it with save_skill; when you learn a "
    "durable fact about his work, save it with remember. Never "
    "store a secret or a password."
)


def orientation_text(lang: str | None = None) -> str:
    """نصّ التوجيه المدمج بلغة الواجهة الحالية (العربية عند أي تعذّر)."""
    if lang is None:
        try:
            lang = i18n.get_lang()
        except Exception:
            lang = "ar"
    return ORIENTATION_EN if lang == "en" else ORIENTATION_AR


# استخراج نصوص الوثائق (docx/xlsx/pdf/نصّية) يعيش في documents.py
# منذ 3.6.0 — قارئ عام واحد (extract_text) لـ read_document
# والمرفقات معاً؛ لا تنفيذ ثانٍ هنا.

class ChatCancelled(Exception):
    """أُلغيت المحادثة تعاونياً: رفعها send_message حين يطلب should_cancel.

    يستعملها مشغّل المهام (tasks.py) لإيقاف مهمة قيد التنفيذ بين
    الجولات دون قتل الخيط؛ المحادثة العادية لا تصادفها إطلاقاً.
    """


def default_data_dir() -> Path:
    """مجلد البيانات الافتراضي: ~/.krouchi_dz (محلي أولاً)."""
    return Path.home() / ".krouchi_dz"


class ChatEngine:
    """واجهة البرنامج الأساسية: بوتات، محادثة بذاكرة، إجراءات عبر الوسيط."""

    def __init__(
        self,
        data_dir: str | Path,
        providers_path: str | Path | None = None,
        ask_callback=None,
        ask_timeout: float = 60.0,
        transport=None,
        provider_factory=None,
        get_transport=None,
        approval_registry=None,
        input_sink=None,
        screen_source=None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "krouchi_dz.db")
        self.secrets = SecretsStore(self.data_dir / "secrets.json")
        providers_file = (
            Path(providers_path)
            if providers_path
            else self.data_dir / "providers.json"
        )
        self.providers_path = providers_file
        self.providers: dict[str, ProviderConfig] = load_providers(providers_file)
        # مزامنة تعريفات المزوّدين إلى القاعدة (مرجع السرّ فقط — بلا مفاتيح).
        for cfg in self.providers.values():
            self.db.upsert_provider(
                cfg.name, cfg.kind, cfg.base_url, cfg.secret_ref, cfg.default_model
            )
        # سجلّ الموافقات المشترك (اختياري): إن مُرّر يحسم طلبات نمط ask
        # أيُّ واجهة تصل إليه (بطاقة الواجهة أو خادم الهاتف) — انظر broker.py.
        self.approval_registry = approval_registry
        self.broker = ApprovalBroker(
            ask_callback=ask_callback,
            ask_timeout=ask_timeout,
            audit=self.db.log_audit,
            registry=approval_registry,
        )
        self.transport = transport
        self.provider_factory = provider_factory or (
            lambda cfg, key: build_provider(cfg, key, transport=self.transport)
        )
        # مصرف إدخال remote (حقن لوحة المفاتيح) لأداتي type_text
        # وpress_keys — قابل للحقن في الاختبارات، ويُنشأ كسولاً من
        # remote.create_input_sink عند أول استعمال فعلي (انظر
        # _get_input_sink)، فيبقى إنشاء المحرّك بلا أي أثر جانبي.
        self.input_sink = input_sink
        # مصدر شاشة remote (التقاط العينين) لأداة see_screen — قابل
        # للحقن في الاختبارات، ويُنشأ كسولاً من remote.create_screen_source
        # عند أول استعمال فعلي (انظر _get_screen_source)، فيبقى إنشاء
        # المحرّك بلا أي أثر جانبي.
        self.screen_source = screen_source
        # نقل GET لاكتشاف النماذج (قابل للحقن في الاختبارات — بلا شبكة).
        self.get_transport = get_transport
        self._provider_cache: dict[str, object] = {}

    # -- إدارة البوتات والمفاتيح ------------------------------------------
    def create_bot(
        self, name: str, provider_name: str | None = None, **kwargs
    ) -> int:
        """ينشئ بوتاً. بلا مزوّد صريح (None) تُحفَظ لقطة اسم مزوّد
        الواجهة المشتركة الحالية (أو '' إن لم تُضبَط بعد — العمود
        NOT NULL و'' صالحة)؛ والاسم الصريح يُتحقَّق منه كالسابق.
        المحادثة نفسها لا تستعمل هذه اللقطة إطلاقاً: الحسم عند
        الإرسال من الواجهة المشتركة وحدها (انظر send_message)."""
        if provider_name is None:
            shared = self.get_shared_api()
            provider_name = shared[0] if shared is not None else ""
        elif provider_name not in self.providers:
            raise ValueError(f"مزوّد غير معروف: {provider_name}")
        return self.db.create_bot(name, provider_name, **kwargs)

    # -- الواجهة المشتركة: API واحدة لكل البوتات ---------------------------
    def get_shared_api(self) -> tuple[str, str] | None:
        """(اسم المزوّد، النموذج) للواجهة المشتركة، أو None إن لم تُضبَط.

        تُشغَّل الهجرة كسولاً أولاً (ensure_shared_api)؛ وإن كان
        المزوّد المحفوظ غير موجود في تعريفات المزوّدين الحالية
        فالواجهة غير مضبوطة (None) مهما كان النموذج المحفوظ.
        """
        self.ensure_shared_api()
        name = self.db.get_setting(SETTING_SHARED_PROVIDER, "")
        if not name or name not in self.providers:
            return None
        return (name, self.db.get_setting(SETTING_SHARED_MODEL, ""))

    def set_shared_api(self, provider_name: str, model: str) -> None:
        """يضبط الواجهة المشتركة (تُدخَل مرة واحدة وتعمل لكل البوتات)."""
        if provider_name not in self.providers:
            raise ValueError(f"مزوّد غير معروف: {provider_name}")
        self.db.set_setting(SETTING_SHARED_PROVIDER, provider_name)
        self.db.set_setting(SETTING_SHARED_MODEL, model or "")

    def ensure_shared_api(self) -> None:
        """هجرة لمرة واحدة إلى الواجهة المشتركة — لا تمسّ ضبطاً قائماً.

        القاعدة حرفياً: إن كان إعداد shared_provider فارغاً وكانت
        التعريفات غير فارغة: اختر أول مزوّد (بترتيب القاموس) له
        مفتاح محفوظ (provider_configured)؛ فإن لم يوجد أي مفتاح
        اختر أول مزوّد. والنموذج: بين البوتات التي مزوّدها المخزَّن
        هو المختار ونموذجها غير فارغ، نموذجُ البوت الأحدث نشاطاً
        (أحدث created_at لمحادثاته/رسائله)؛ فإن لم يوجد بوت مؤهّل
        يبقى النموذج ''. يُحفَظ shared_provider دائماً في هذا الفرع،
        وshared_model فقط إن وُجد نموذج. بلا مزوّدين: لا يُحفَظ شيء.
        العملية كسولة ومكرَّرة بأمان (idempotent): ما إن يُحفَظ
        shared_provider حتى لا تعود تعمل أبداً.
        """
        if self.db.get_setting(SETTING_SHARED_PROVIDER, ""):
            return
        if not self.providers:
            return
        chosen = None
        for name in self.providers:
            if self.provider_configured(name):
                chosen = name
                break
        if chosen is None:
            chosen = next(iter(self.providers))
        activity = self.db.bot_last_activity()
        best_model = ""
        best_at: str | None = None
        for bot in self.db.list_bots():
            if bot["provider_name"] != chosen or not bot["model"]:
                continue
            at = activity.get(bot["id"], "")
            if best_at is None or at > best_at:
                best_at, best_model = at, bot["model"]
        self.db.set_setting(SETTING_SHARED_PROVIDER, chosen)
        if best_model:
            self.db.set_setting(SETTING_SHARED_MODEL, best_model)

    def set_api_key(self, provider_name: str, api_key: str) -> None:
        """يحفظ مفتاح مزوّد في ملف الأسرار (لا في القاعدة)."""
        cfg = self.providers.get(provider_name)
        if cfg is None:
            raise ValueError(f"مزوّد غير معروف: {provider_name}")
        self.secrets.set(cfg.secret_ref, api_key)
        self._provider_cache.pop(provider_name, None)

    def provider_configured(self, provider_name: str) -> bool:
        cfg = self.providers.get(provider_name)
        return bool(cfg and self.secrets.has(cfg.secret_ref))

    def _get_provider(self, provider_name: str):
        if provider_name not in self._provider_cache:
            cfg = self.providers[provider_name]
            key = self.secrets.get(cfg.secret_ref)
            self._provider_cache[provider_name] = self.provider_factory(cfg, key)
        return self._provider_cache[provider_name]

    def _get_input_sink(self):
        """مصرف إدخال remote — يُنشأ كسولاً عند أول استعمال.

        المصرف نفسه الذي يقوده خادم الهاتف لمسار /api/input
        (server.get_input_sink): على ويندوز حقن SendInput حقيقي
        (remote.WindowsInputSink)، وعلى غيره NullInputSink يرفع
        خطأ عربياً واضحاً عند الاستعمال — فلا تنفيذ ثانٍ للحقن هنا.
        """
        if self.input_sink is None:
            self.input_sink = remote.create_input_sink()
        return self.input_sink

    def _get_screen_source(self):
        """مصدر شاشة remote — يُنشأ كسولاً عند أول استعمال.

        المصدر نفسه الذي يقوده خادم الهاتف لمسار /api/screen/frame
        (server.get_screen_source): على ويندوز التقاط حقيقي
        (Pillow/ImageGrab مفضّلاً)، وعلى غيره UnsupportedScreenSource
        يرفع RuntimeError عربياً واضحاً عند الالتقاط — فلا تنفيذ
        ثانٍ للالتقاط هنا.
        """
        if self.screen_source is None:
            self.screen_source = remote.create_screen_source()
        return self.screen_source

    # -- إدخال API: أي مفتاح + أي عنوان، والبرنامج يكتشف المزوّد بنفسه -------
    def _save_providers_file(self) -> None:
        save_providers(self.providers_path, self.providers)

    def _unique_provider_name(self, wanted: str) -> str:
        base = sanitize_name(wanted)
        if base not in self.providers:
            return base
        counter = 2
        while f"{base}-{counter}" in self.providers:
            counter += 1
        return f"{base}-{counter}"

    def add_custom_provider(
        self,
        base_url: str,
        api_key: str,
        name: str | None = None,
        kind: str | None = None,
    ) -> ProviderConfig:
        """يسجّل مزوّداً من عنوان + مفتاح فقط (بلا أي اتصال بالشبكة).

        العنوان يُطبَّع (شرطة أخيرة، /v1، لاحقة كاملة...)، والنوع يُخمَّن
        من الخادم ما لم يُمرَّر صراحة، والاسم يُشتق من الخادم إن غاب.
        المفتاح يذهب لملف الأسرار فقط؛ المزوّد يبدأ «غير مُتحقَّق» حتى
        ينجح اكتشاف النماذج. إعادة إدخال نفس العنوان تحدّث مفتاحه.
        يرفع ValueError برسالة عربية إن كان العنوان غير صالح.
        """
        resolved_kind = classify_kind(base_url, kind)
        canonical = normalize_base_url(base_url, resolved_kind)
        for cfg in self.providers.values():
            if cfg.base_url == canonical:
                # نفس العنوان مسجّل أصلاً: حدّث المفتاح وأعد التعريف.
                self.secrets.set(cfg.secret_ref, api_key)
                self._provider_cache.pop(cfg.name, None)
                return cfg
        provider_name = self._unique_provider_name(name or derive_name(canonical))
        cfg = ProviderConfig(
            name=provider_name,
            kind=resolved_kind,
            base_url=canonical,
            secret_ref=provider_name,
            default_model="",
            verified=False,
        )
        self.providers[provider_name] = cfg
        self.secrets.set(cfg.secret_ref, api_key)
        self.db.upsert_provider(
            cfg.name, cfg.kind, cfg.base_url, cfg.secret_ref, cfg.default_model
        )
        self._save_providers_file()
        return cfg

    def fetch_models(
        self, provider_name: str, force: bool = False
    ) -> DiscoveryResult:
        """يجلب نماذج مزوّد مسجّل (من الكاش إن كان حديثاً، وإلا من الشبكة).

        النجاح يعلّم المزوّد «مُتحقَّقاً» ويحفظ النماذج ووقتها في ملف
        الإعدادات؛ الفشل يعيد DiscoveryResult برسالة عربية واضحة ولا
        ينهار — ويُسقِط علامة التحقق لأن آخر محاولة لم تنجح.
        """
        cfg = self.providers.get(provider_name)
        if cfg is None:
            raise ValueError(f"مزوّد غير معروف: {provider_name}")
        if not force and cfg.models and cfg.models_fetched_at:
            try:
                fetched = datetime.fromisoformat(cfg.models_fetched_at)
                age = (datetime.now(timezone.utc) - fetched).total_seconds()
            except ValueError:
                age = MODELS_CACHE_TTL + 1
            if age < MODELS_CACHE_TTL:
                return DiscoveryResult(
                    ok=True,
                    provider=cfg.name,
                    models=list(cfg.models),
                    verified=cfg.verified,
                    from_cache=True,
                    base_url=cfg.base_url,
                )
        api_key = self.secrets.get(cfg.secret_ref)
        if not api_key:
            return DiscoveryResult(
                ok=False,
                provider=cfg.name,
                error=ERR_NO_KEY,
                error_kind="no_key",
                verified=False,
                base_url=cfg.base_url,
            )
        try:
            models = discover_models(
                cfg.base_url, api_key, cfg.kind, get_transport=self.get_transport
            )
        except DiscoveryError as exc:
            cfg.verified = False
            self._save_providers_file()
            return DiscoveryResult(
                ok=False,
                provider=cfg.name,
                error=exc.message,
                error_kind=exc.kind,
                verified=False,
                base_url=cfg.base_url,
            )
        cfg.models = models
        cfg.models_fetched_at = datetime.now(timezone.utc).isoformat()
        cfg.verified = True
        if not cfg.default_model:
            cfg.default_model = models[0]
            self.db.upsert_provider(
                cfg.name, cfg.kind, cfg.base_url, cfg.secret_ref, cfg.default_model
            )
        self._provider_cache.pop(cfg.name, None)
        self._save_providers_file()
        return DiscoveryResult(
            ok=True,
            provider=cfg.name,
            models=list(models),
            verified=True,
            base_url=cfg.base_url,
        )

    def add_api(
        self,
        base_url: str,
        api_key: str,
        name: str | None = None,
        kind: str | None = None,
    ) -> DiscoveryResult:
        """★ نقطة الدخول الأولى لإدخال API — مثل DeepSeek Harness.

        أعطِ العنوان والمفتاح فقط (الاسم اختياري: يُشتق من الخادم)،
        فيسجّل البرنامج المزوّد ويكتشف نماذجه المتاحة في خطوة واحدة.
        النتيجة DiscoveryResult: عند النجاح result.models هي قائمة
        النماذج الجاهزة لصنع بوت؛ وعند الفشل result.error رسالة عربية
        واضحة تشرح السبب — والمزوّد يبقى محفوظاً مُعلَّماً «غير مُتحقَّق».
        """
        try:
            cfg = self.add_custom_provider(base_url, api_key, name=name, kind=kind)
        except ValueError as exc:
            return DiscoveryResult(
                ok=False, error=str(exc), error_kind="bad_url", verified=False
            )
        return self.fetch_models(cfg.name, force=True)

    # اسم بديل صريح بنفس السلوك (تسجيل + جلب في نداء واحد).
    def register_and_fetch(
        self,
        base_url: str,
        api_key: str,
        name: str | None = None,
        kind: str | None = None,
    ) -> DiscoveryResult:
        return self.add_api(base_url, api_key, name=name, kind=kind)

    # -- المحادثة ---------------------------------------------------------
    def _row_to_message(self, row: dict) -> dict:
        msg: dict = {"role": row["role"], "content": row["content"] or ""}
        if row.get("tool_calls_json"):
            msg["tool_calls"] = json.loads(row["tool_calls_json"])
        if row.get("tool_call_id"):
            msg["tool_call_id"] = row["tool_call_id"]
        return msg

    def history(self, bot_id: int) -> list[dict]:
        conv_id = self.db.get_or_create_conversation(bot_id)
        return self.db.get_messages(conv_id)

    def learning_context(self, bot_id: int, lang: str | None = None) -> str:
        """سياق التعلّم المحقون في موجّه النظام بعد التوجيه المدمج:
        فهرس المهارات (سطر لكل مهارة: الاسم — الوصف) ثم ملاحظات
        الذاكرة (المشتركة + ملاحظات هذا البوت، الأحدث 20، الأقدم
        أولاً). سلسلة فارغة إن لم توجد مهارات ولا ملاحظات — فتبقى
        موجّهات البوتات الجدد كما كانت حرفياً."""
        if lang is None:
            try:
                lang = i18n.get_lang()
            except Exception:
                lang = "ar"
        skills = self.db.list_skills()
        notes = self.db.memory_for_prompt(bot_id)
        if not skills and not notes:
            return ""
        lines: list[str] = []
        if lang == "en":
            if skills:
                lines.append(
                    "Your saved skills (before a familiar task, call "
                    "use_skill with a name to read its full "
                    "instructions and follow them):"
                )
                for skill in skills:
                    line = f"- {skill['name']}"
                    if skill["description"]:
                        line += f" — {skill['description']}"
                    lines.append(line)
            if notes:
                lines.append(
                    "Your saved memory (durable facts about the "
                    "director's work — take them into account):"
                )
                lines.extend(f"- {note['fact']}" for note in notes)
        else:
            if skills:
                lines.append(
                    "مهاراتك المحفوظة (قبل أي مهمة مألوفة اقرأ مهارة "
                    "الموضوع بـ use_skill واتّبع تعليماتها):"
                )
                for skill in skills:
                    line = f"- {skill['name']}"
                    if skill["description"]:
                        line += f" — {skill['description']}"
                    lines.append(line)
            if notes:
                lines.append(
                    "ذاكرتك المحفوظة (حقائق دائمة عن عمل المدير — "
                    "خُذها بعين الاعتبار):"
                )
                lines.extend(f"- {note['fact']}" for note in notes)
        return "\n".join(lines)

    def send_message(
        self,
        bot_id: int,
        text: str,
        should_cancel=None,
        on_event=None,
        task_id: int | None = None,
        attachments: list[dict] | None = None,
    ) -> str:
        """يرسل رسالة لبوت ويعيد ردّه النهائي (مع حلقة أدوات عند الحاجة).

        المعاملات الإضافية اختيارية وسلوك غيابها هو السلوك القائم حرفياً:
        - should_cancel: دالة بلا معاملات تُستشار بين الجولات وقبل كل
          أداة؛ إن أعادت True رُفعت ChatCancelled (إلغاء تعاوني).
        - on_event: ردّ نداء (kind, text) يتلقّى أحداث التنفيذ (أدوات…)
          — يستعمله مشغّل المهام لبناء سجلّ المهمة.
        - task_id: سياق مهمة مالكة، يُحمل إلى طلبات الموافقة.
        - attachments: مرفقات مهيّأة بـ prepare_attachment (زرّ +):
          نصّية تلتحم بالرسالة تحت عنوان «📎 ملف مرفق: الاسم»، وصور
          تُسلَّم أجزاءَ صورة في الرسالة الحيّة فقط (قاعدة البيانات
          تحفظ نصاً فقط: نصّ المرفقات وسطر «📎 صورة مرفقة: الاسم»).
          نموذج نصّي يرفض الصورة ⇒ تدهور آمن لنصّ إرشادي كـ see_screen.
        """
        bot = self.db.get_bot(bot_id)
        if bot is None:
            raise ValueError(f"بوت غير موجود: {bot_id}")
        # الحسم من الواجهة المشتركة وحدها: مزوّد البوت ونموذجه
        # المخزَّنان لا يُستعملان إطلاقاً — API واحدة لكل البوتات.
        shared = self.get_shared_api()
        if shared is None:
            raise ValueError(
                "لم تُضبط الواجهة المشتركة بعد — أضف واجهة API "
                "واختر نموذجاً واحداً لكل البوتات"
            )
        shared_name, model = shared
        if not model:
            raise ValueError("اختر نموذجاً للواجهة المشتركة أولاً")
        provider = self._get_provider(shared_name)
        conv_id = self.db.get_or_create_conversation(bot_id)

        def _check_cancel() -> None:
            if should_cancel is not None and should_cancel():
                raise ChatCancelled("أُلغيت المحادثة بطلب الإلغاء")

        messages: list[dict] = []
        # التوجيه المدمج أولاً دائماً، ثم سياق التعلّم (فهرس
        # المهارات + الذاكرة)، وتعليمات البوت الخاصة أخيراً.
        system_content = orientation_text()
        learning = self.learning_context(bot_id)
        if learning:
            system_content += "\n\n" + learning
        if bot["system_prompt"]:
            system_content += "\n\n" + bot["system_prompt"]
        messages.append({"role": "system", "content": system_content})
        messages.extend(
            self._row_to_message(r) for r in self.db.get_messages(conv_id)
        )
        # المرفقات (زرّ +): النصّية تلتحم بالرسالة المخزَّنة تحت
        # عنوان واضح؛ والصور تُذكر بسطر واحد في المخزَّن وتُسلَّم
        # أجزاءَ صورة في الرسالة الحيّة فقط — كصور see_screen.
        stored_text = text
        attach_blocks: list[str] = []
        attach_images: list[dict] = []
        for attachment in attachments or []:
            if not isinstance(attachment, dict):
                continue
            kind = attachment.get("kind")
            name = str(attachment.get("name") or "ملف")
            if kind == "text" and attachment.get("text"):
                attach_blocks.append(f"📎 ملف مرفق: {name}\n{attachment['text']}")
            elif kind == "image" and attachment.get("data_uri"):
                attach_images.append(attachment)
        if attach_blocks:
            stored_text = (
                (stored_text + "\n\n") if stored_text else ""
            ) + "\n\n".join(attach_blocks)
        if attach_images:
            names = "، ".join(
                str(a.get("name") or "صورة") for a in attach_images
            )
            stored_text = (
                (stored_text + "\n\n") if stored_text else ""
            ) + f"📎 صورة مرفقة: {names}"
        self.db.add_message(conv_id, "user", stored_text)
        attach_parts_msg: dict | None = None
        attach_fallback = ""
        if attach_images and getattr(provider, "supports_vision", True):
            parts: list[dict] = [{"type": "text", "text": stored_text}]
            for attachment in attach_images:
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": attachment["data_uri"]},
                    }
                )
            attach_parts_msg = {"role": "user", "content": parts}
            attach_fallback = stored_text + "\n\n" + ATTACH_VISION_UNSUPPORTED_TEXT
            messages.append(attach_parts_msg)
        elif attach_images:
            # مزوّد معروف بأنه نصّي فقط: النصّ الإرشادي منذ البداية.
            messages.append(
                {
                    "role": "user",
                    "content": stored_text
                    + "\n\n"
                    + ATTACH_VISION_UNSUPPORTED_TEXT,
                }
            )
        else:
            messages.append({"role": "user", "content": stored_text})

        # مراجع رسالة صورة see_screen المعلّقة داخل messages الحيّة:
        # (رسالة نتيجة الأداة، رسالة الصورة) — ليتسنّى التدهور الآمن
        # إن رفض المزوّد الصورة في النداء التالي (نموذج نصّي).
        vision_tool_msg: dict | None = None
        vision_image_msg: dict | None = None

        for _round in range(MAX_TOOL_ROUNDS + 1):
            _check_cancel()
            try:
                result: ChatResult = provider.chat(messages, model, tools=TOOLS)
            except ProviderError as exc:
                if attach_parts_msg is not None and _is_vision_rejection(exc):
                    # صورة مرفقة رفضها نموذج نصّي: تتحوّل رسالة
                    # الأجزاء إلى نصّ الرسالة + النصّ الإرشادي،
                    # وتُعاد المحاولة نصّياً فقط — تدهور see_screen
                    # نفسه للمرفقات.
                    attach_parts_msg["content"] = attach_fallback
                    attach_parts_msg = None
                    continue
                if vision_image_msg is not None and _is_vision_rejection(exc):
                    # تدهور آمن: تُحذف رسالة الصورة من المحادثة
                    # الحيّة وتُستبدَل نتيجة الأداة بالنصّ الإرشادي،
                    # ثم تُعاد محاولة النداء نصّياً فقط — فتصل
                    # الإرشادات للنموذج بدل الانهيار أو الردّ الفارغ.
                    for idx, msg in enumerate(messages):
                        if msg is vision_image_msg:
                            del messages[idx]
                            break
                    if vision_tool_msg is not None:
                        vision_tool_msg["content"] = VISION_UNSUPPORTED_TEXT
                    vision_tool_msg = None
                    vision_image_msg = None
                    continue
                raise
            # نجح النداء: أي صورة معلّقة قُبلت، فتُصفَّى المراجع.
            vision_tool_msg = None
            vision_image_msg = None
            if not result.tool_calls:
                self.db.add_message(conv_id, "assistant", result.text)
                return result.text
            api_calls = [tc.to_api_dict() for tc in result.tool_calls]
            self.db.add_message(
                conv_id,
                "assistant",
                result.text,
                tool_calls_json=json.dumps(api_calls, ensure_ascii=False),
            )
            messages.append(
                {"role": "assistant", "content": result.text, "tool_calls": api_calls}
            )
            for tc in result.tool_calls:
                _check_cancel()
                outcome = self.perform_action(
                    bot_id, tc.name, tc.arguments,
                    task_id=task_id, on_event=on_event,
                )
                content = outcome["output"] if outcome["ok"] else outcome["error"]
                image = outcome.get("image") if outcome["ok"] else None
                if image is not None and not getattr(
                    provider, "supports_vision", True
                ):
                    # مزوّد معروف بأنه نصّي فقط (supports_vision=False):
                    # لا صورة تُدخَل أصلاً — نتيجة الأداة هي النصّ
                    # الإرشادي نفسه منذ البداية.
                    content = VISION_UNSUPPORTED_TEXT
                    image = None
                self.db.add_message(
                    conv_id, "tool", content, tool_call_id=tc.id
                )
                tool_msg = {
                    "role": "tool", "tool_call_id": tc.id, "content": content,
                }
                messages.append(tool_msg)
                if image is not None:
                    # الصورة تُسلَّم جزءَ صورة حقيقياً في رسالة مستخدم
                    # تالية لنتيجة الأداة — في المحادثة الحيّة فقط،
                    # لا في قاعدة البيانات (فلا تنتفخ الذاكرة المحفوظة
                    # بصور base64، وتبقى سلوكيات الأدوات النصّية كما هي).
                    question = image.get("question") or ""
                    text_part = question if question else (
                        "هذه صورة شاشة حاسوب المستخدم الآن. انظر إليها، "
                        "وصِف باختصار ما تراه، ثم تابع تنفيذ طلب المستخدم."
                    )
                    vision_image_msg = {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": text_part},
                            {
                                "type": "image_url",
                                "image_url": {"url": image["data_uri"]},
                            },
                        ],
                    }
                    messages.append(vision_image_msg)
                    vision_tool_msg = tool_msg
        notice = "توقّف البوت: تجاوز الحدّ الأقصى لجولات الأدوات في رسالة واحدة."
        self.db.add_message(conv_id, "assistant", notice)
        return notice

    # -- تنفيذ الإجراءات عبر الوسيط ----------------------------------------
    def perform_action(
        self,
        bot_id: int,
        action: str,
        params: dict | None = None,
        task_id: int | None = None,
        on_event=None,
    ) -> dict:
        """يطلب تنفيذ إجراء عبر وسيط الموافقات؛ يعيد {ok, output|error}.

        on_event (اختياري): يُبلَّغ بحدث «tool» قبل التنفيذ وبنتيجته
        بعده — لبناء سجلّ المهام. task_id: سياق المهمة المالكة.
        """
        params = params or {}
        bot = self.db.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": f"بوت غير موجود: {bot_id}"}
        if on_event is not None:
            on_event("tool", action)
        if action == "list_windows":
            # قراءة محضة (سرد نوافذ): لا تغيّر شيئاً على الجهاز،
            # فتُنفَّذ مباشرة بلا وسيط موافقات — وتعمل في كل الأنماط.
            try:
                output = self._do_list_windows(params)
            except Exception as exc:
                return {"ok": False, "error": f"فشل تنفيذ {action}: {exc}"}
            return {"ok": True, "output": output}
        # أداة window_action تُسجَّل عند الوسيط بنوع تحكّم الهاتف نفسه
        # «window_control» — بطاقة موافقة وسجلّ تدقيق واحد للمسارين.
        broker_action = "window_control" if action == "window_action" else action
        decision = self.broker.authorize(
            bot, broker_action, params, task_id=task_id,
            # مسح المحادثة لا رجعة فيه: يُسأل المستخدم دائماً ولو كان
            # وضع البوت «full» (سابقة «power» نفسها عبر force_ask).
            force_ask=action == "clear_conversation",
        )
        if not decision.allowed:
            if on_event is not None:
                on_event("tool_denied", f"{action}: {decision.reason}")
            return {"ok": False, "error": f"رُفض الإجراء ({decision.reason})"}
        try:
            if action == "read_file":
                output = self._do_read_file(params)
            elif action == "read_document":
                output = self._do_read_document(params)
            elif action == "read_clipboard":
                output = self._do_read_clipboard(params)
            elif action == "see_screen":
                output, image = self._do_see_screen(params)
                return {"ok": True, "output": output, "image": image}
            elif action == "write_file":
                output = self._do_write_file(params)
            elif action == "run_command":
                output = self._do_run_command(params)
            elif action == "open_target":
                output = self._do_open_target(params)
            elif action == "window_action":
                output = self._do_window_action(params)
            elif action == "type_text":
                output = self._do_type_text(params)
            elif action == "press_keys":
                output = self._do_press_keys(params)
            elif action == "clear_conversation":
                output = self._do_clear_conversation(bot_id)
            elif action == "use_skill":
                output = self._do_use_skill(params)
            elif action == "save_skill":
                output = self._do_save_skill(params)
            elif action == "remember":
                output = self._do_remember(bot_id, params)
            else:
                return {"ok": False, "error": f"إجراء غير معروف: {action}"}
        except Exception as exc:  # خطأ تنفيذ يُعاد للنموذج/المستخدم كنتيجة
            return {"ok": False, "error": f"فشل تنفيذ {action}: {exc}"}
        return {"ok": True, "output": output}

    def authorize_control(
        self, action: str, params: dict | None = None, force_ask: bool = False
    ):
        """موافقة على فعل تحكّم مباشر من الهاتف (بلا بوت مالك).

        طلبات التحكّم (تشغيل أمر، فتح هدف، طاقة) تمرّ بالوسيط نفسه
        وسجلّه المشترك، باسم «تحكّم الهاتف» ونمط ask — فتظهر في
        /api/approvals وتحسمها أي واجهة كطلبات البوتات تماماً.
        force_ask=True (للطاقة) يلغي أي اختصار نمط: السؤال واجب دائماً.
        يعيد BrokerDecision.
        """
        bot = {"id": None, "name": "تحكّم الهاتف", "approval_mode": "ask"}
        return self.broker.authorize(
            bot, action, params or {}, force_ask=force_ask
        )

    @staticmethod
    def _do_read_file(params: dict) -> str:
        path = Path(params["path"])
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n…[قُطع: الملف أكبر من الحدّ]"
        return text

    @staticmethod
    def _do_read_document(params: dict) -> str:
        # استخراج نصّ وثيقة عبر القارئ العام الواحد
        # (documents.extract_text): docx وxlsx بمسار استخراج حقيقي،
        # وPDF بأفضل جهد من نصّه المخزَّن، والامتدادات النصّية بفكّ
        # الترميز التراجعي (ملفات ويندوز العربية cp1256 مقروءة صح)،
        # وHTML يُجرَّد إلى نصّ عادي. الأخطاء كلها ValueError عربية
        # واضحة يحوّلها perform_action إلى نتيجة خطأ للنموذج —
        # بلا انهيار.
        raw_path = params.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("مسار الوثيقة فارغ أو غير صالح")
        path = Path(raw_path.strip())
        if not path.is_file():
            raise ValueError(f"الملف غير موجود: {path}")
        text = extract_text(path.read_bytes(), path.name)
        if not text.strip():
            return "الوثيقة لا تحوي نصاً قابلاً للقراءة"
        return _truncate_doc_text(text)

    @staticmethod
    def _do_read_clipboard(params: dict) -> str:
        # قارئ مسار تحكّم الهاتف نفسه (GET /api/clipboard):
        # control.get_clipboard — لا تنفيذ ثانٍ لقراءة الحافظة هنا.
        # القارئ يعيد سلسلة فارغة عند التعذّر أو غياب النصّ،
        # فتُترجَم هنا إلى نتيجة عربية واضحة للنموذج.
        text = control.get_clipboard()
        if not text:
            return "الحافظة فارغة (لا نصّ فيها الآن، أو ما فيها ليس نصاً)"
        if len(text) > MAX_DOC_CHARS:
            text = text[:MAX_DOC_CHARS] + (
                f"\n…[قُطع النصّ عند {MAX_DOC_CHARS} حرف: "
                "نصّ الحافظة أطول من ذلك ويستمرّ بعد هذا الموضع]"
            )
        return text

    def _do_see_screen(self, params: dict):
        # عينا البوت (الإصدار 3.5.0): التقاط بمسار /api/screen/frame
        # نفسه — remote.create_screen_source().grab_jpeg (Pillow/
        # ImageGrab مفضّلاً على ويندوز) — فلا تنفيذ ثانٍ للالتقاط
        # هنا. يعيد (نصّ نتيجة الأداة، قاموس الصورة {data_uri,
        # question}) فيسلّمها send_message للنموذج جزءَ صورة حقيقياً.
        # فشل الالتقاط (RuntimeError من المصدر غير المدعوم على هذه
        # المنصّة) يصعد فيحوّله perform_action إلى نتيجة خطأ عربية
        # واضحة — كسائر أدوات التحكّم، بلا انهيار.
        question = params.get("question")
        if question is not None and not isinstance(question, str):
            raise ValueError("سؤال الرؤية يجب أن يكون نصاً")
        source = self._get_screen_source()
        data = source.grab_jpeg(
            max_width=SCREEN_IMAGE_MAX_WIDTH, quality=SCREEN_IMAGE_QUALITY
        )
        if not data:
            raise ValueError("تعذّر التقاط الشاشة (إطار فارغ)")
        data_uri = (
            "data:image/jpeg;base64,"
            + base64.b64encode(data).decode("ascii")
        )
        output = (
            "التُقطت صورة الشاشة الحالية وأُرفقت لك لتراها في الرسالة "
            "التالية. انظر إليها وصِف باختصار ما تراه ثم تصرّف بناءً عليه."
        )
        return output, {
            "data_uri": data_uri,
            "question": (question or "").strip(),
        }

    @staticmethod
    def _do_write_file(params: dict) -> str:
        path = Path(params["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(params.get("content", ""), encoding="utf-8")
        return f"كُتب الملف: {path} ({path.stat().st_size} بايت)"

    @staticmethod
    def _do_open_target(params: dict) -> str:
        # نفس تنفيذ مسار تحكّم الهاتف (/api/open): control.open_target
        # يفتح الهدف بالتطبيق الافتراضي للنظام فيظهر مرئياً على الشاشة.
        target = params.get("target")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("هدف فتح فارغ")
        target = target.strip()
        control.open_target(target)
        return f"فُتح الهدف على الحاسوب: {target}"

    @staticmethod
    def _do_list_windows(params: dict) -> str:
        # نفس تنفيذ مسار تحكّم الهاتف (GET /api/windows): control.list_windows
        windows = control.list_windows()
        if not windows:
            return "لا نوافذ مفتوحة ذات عناوين الآن"
        lines = [f"النوافذ المفتوحة ({len(windows)}):"]
        for window in windows:
            lines.append(f"- {window.get('id')}: {window.get('title')}")
        return "\n".join(lines)

    @staticmethod
    def _do_window_action(params: dict) -> str:
        # نفس تنفيذ مسار تحكّم الهاتف (POST /api/window) وبنفس
        # التحقّق: معرّف رقمي (نصّ رقمي يُحوَّل) وفعل من WINDOW_ACTIONS،
        # ثم control.default_window_executor نفسه.
        window_id = params.get("id")
        if isinstance(window_id, str) and window_id.strip().lstrip("-").isdigit():
            window_id = int(window_id)
        action = params.get("action")
        if (
            not isinstance(window_id, int)
            or isinstance(window_id, bool)
            or action not in control.WINDOW_ACTIONS
        ):
            raise ValueError(
                "الحقول المطلوبة: id (رقم) و action "
                "(focus|minimize|maximize|close)"
            )
        control.default_window_executor(window_id, action)
        labels = {
            "focus": "فُعّلت النافذة وأُظهرت في المقدمة",
            "minimize": "صُغّرت النافذة",
            "maximize": "كُبّرت النافذة",
            "close": "أُغلقت النافذة",
        }
        return f"{labels[action]}: {window_id}"

    def _do_type_text(self, params: dict) -> str:
        # نفس مسار إدخال الهاتف (POST /api/input) حرفياً:
        # remote.dispatch_input يتحقّق من الحدث ثم يقود مصرف الإدخال
        # نفسه (حقن يونيكود SendInput على ويندوز) — لا تنفيذ ثانٍ
        # للحقن هنا. النص الأطول من حدّ الحدث الواحد يُجزّأ على
        # حدوده فيُكتب كاملاً مهما طال (رسالة أو محضر في Word).
        text = params.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("النص فارغ أو غير صالح")
        sink = self._get_input_sink()
        for start in range(0, len(text), TEXT_EVENT_MAX):
            remote.dispatch_input(
                sink, None,
                {"type": "text", "text": text[start:start + TEXT_EVENT_MAX]},
            )
        return f"كُتب النص في النافذة المركّزة ({len(text)} حرفاً)"

    def _do_press_keys(self, params: dict) -> str:
        # تحليل «ctrl+s» ونحوها إلى أحداث remote نفسها التي يقودها
        # مسار إدخال الهاتف: مفتاح وحيد = حدث «key»، ومع مفاتيح
        # تعديل = حدث «combo» بقائمة المفاتيح. التحقّق من الأسماء
        # (وأخطاؤه العربية) من remote.validate_input_event نفسه.
        raw = params.get("keys")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("المفاتيح فارغة أو غير صالحة")
        parts = [part.strip().lower() for part in raw.split("+")]
        if any(not part for part in parts):
            raise ValueError(f"تركيبة مفاتيح غير صالحة: {raw}")
        sink = self._get_input_sink()
        if len(parts) == 1:
            remote.dispatch_input(sink, None, {"type": "key", "key": parts[0]})
            return f"ضُغط المفتاح في النافذة المركّزة: {parts[0]}"
        remote.dispatch_input(sink, None, {"type": "combo", "keys": parts})
        return f"ضُغطت التركيبة في النافذة المركّزة: {'+'.join(parts)}"

    def _do_clear_conversation(self, bot_id: int) -> str:
        # مسح نهائي لسجلّ هذا البوت وحده (db.clear_bot_messages)؛
        # الموافقة مرّت عبر الوسيط بـ force_ask قبل الوصول إلى هنا،
        # والسجلّ يُقرأ من القاعدة في كل جولة فتسري من الجولة التالية.
        deleted = self.db.clear_bot_messages(bot_id)
        return f"مُسح سجلّ محادثة هذا البوت نهائياً ({deleted} رسالة)"

    # -- التعلّم والمهارات (الإصدار 3.6.0) ------------------------------------
    def _do_use_skill(self, params: dict) -> str:
        # قراءة محضة لتعليمات مهارة محفوظة — مرّت بالوسيط بنفس
        # حوكمة read_file (تُسمح في نمط القراءة فقط أيضاً).
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("اسم المهارة فارغ أو غير صالح")
        skill = self.db.get_skill(name.strip())
        if skill is None:
            available = "، ".join(s["name"] for s in self.db.list_skills())
            raise ValueError(
                f"مهارة غير موجودة: {name.strip()} — "
                f"المهارات المتاحة: {available or 'لا مهارات محفوظة بعد'}"
            )
        header = f"مهارة «{skill['name']}»"
        if skill["description"]:
            header += f" — {skill['description']}"
        return header + "\n\n" + skill["instructions"]

    def _do_save_skill(self, params: dict) -> str:
        # حفظ/تحديث مهارة بمصدر «bot» — مرّ بالوسيط كفعل كتابة
        # مشكِّل للسلوك (يسأل في ask ويُرفض في readonly).
        name = params.get("name")
        instructions = params.get("instructions")
        description = params.get("description", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("اسم المهارة فارغ أو غير صالح")
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError("تعليمات المهارة فارغة أو غير صالحة")
        if description is None:
            description = ""
        if not isinstance(description, str):
            raise ValueError("وصف المهارة يجب أن يكون نصاً")
        existed = self.db.get_skill(name.strip()) is not None
        self.db.save_skill(
            name.strip(), description.strip(), instructions,
            origin="bot",
        )
        verb = "حُدّثت" if existed else "حُفظت"
        return f"{verb} المهارة: {name.strip()}"

    def _do_remember(self, bot_id: int, params: dict) -> str:
        # ملاحظة ذاكرة لهذا البوت وحده (bot_id) — مرّت بالوسيط
        # كفعل كتابة كـ save_skill تماماً.
        fact = params.get("fact")
        if not isinstance(fact, str) or not fact.strip():
            raise ValueError("الحقيقة المراد حفظها فارغة أو غير صالحة")
        self.db.add_memory(bot_id, fact.strip())
        return f"حُفظ في ذاكرتك: {fact.strip()}"

    @staticmethod
    def _do_run_command(params: dict) -> str:
        command = params["command"]
        if sys.platform == "win32":
            # ويندوز: التنفيذ عبر صدفة النظام (cmd.exe) بسلسلة الأمر كما
            # هي — فتعمل الأوامر الداخلية (dir وstart...) والمسارات ذات
            # الشرطات الخلفية والاقتباسات كما يتوقّع مستخدم ويندوز.
            # (التقسيم بـshlex مع shell=False كان يكسر ذلك كله:
            # [WinError 2] للأوامر الداخلية وتشويه للمسارات.)
            cmdline = (
                command
                if isinstance(command, str)
                else subprocess.list2cmdline(command)
            )
            if not cmdline.strip():
                raise ValueError("أمر فارغ")
            proc = subprocess.run(
                cmdline,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
                shell=True,
            )
        else:
            argv = command if isinstance(command, list) else shlex.split(command)
            if not argv:
                raise ValueError("أمر فارغ")
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
                shell=False,
            )
        out = (proc.stdout or "") + (proc.stderr or "")
        return f"[رمز الخروج {proc.returncode}]\n{out}".strip()

    def close(self) -> None:
        self.db.close()


# تصدير مريح: اسم المحرّك بوصفه واجهة البرنامج.
__all__ = [
    "ChatEngine",
    "ChatCancelled",
    "default_data_dir",
    "MAX_TOOL_ROUNDS",
    "ORIENTATION_AR",
    "ORIENTATION_EN",
    "orientation_text",
    "SCREEN_IMAGE_MAX_WIDTH",
    "SCREEN_IMAGE_QUALITY",
    "VISION_UNSUPPORTED_TEXT",
    "ATTACH_VISION_UNSUPPORTED_TEXT",
    "prepare_attachment",
    "SETTING_SHARED_PROVIDER",
    "SETTING_SHARED_MODEL",
]
