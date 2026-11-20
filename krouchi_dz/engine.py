"""محرّك المحادثة في Krouchi_DZ — مستقل عن أي واجهة (تقوده واجهة الخطوة 2).

يربط: قاعدة البيانات المحلية، ملف إعدادات المزوّدين، مخزن الأسرار،
ووسيط الموافقات. إرسال رسالة لبوت يحفظ الذاكرة لكل بوت في SQLite،
وإذا طلب النموذج أدوات (read_file / write_file / run_command /
open_target / window_action / type_text / press_keys) نُفّذت عبر الوسيط
فقط، وأُعيدت نتائجها للنموذج ليكمل ردّه. وحدها list_windows قراءة محضة
فتُنفَّذ بلا وسيط. أداتا الكتابة (type_text / press_keys) تقودان مصرف
إدخال remote نفسه الذي يستعمله مسار إدخال الهاتف (/api/input).

ونقطة الدخول الأولى لإدخال API هي add_api(base_url, api_key):
أي عنوان + أي مفتاح، فيسجّل المزوّد ويكتشف نماذجه بنفسه (discovery.py).
"""

from __future__ import annotations

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
from .providers import TOOLS, ChatResult, ToolCall, build_provider
from .secrets import SecretsStore

MAX_TOOL_ROUNDS = 5          # حدّ جولات الأدوات في الرسالة الواحدة
MAX_FILE_CHARS = 200_000     # حدّ حجم القراءة المعادة للنموذج
COMMAND_TIMEOUT = 30.0       # مهلة تنفيذ أمر واحد (ثوانٍ)
TEXT_EVENT_MAX = 2000        # حدّ طول حدث «text» واحد في remote.validate_input_event

# -- الواجهة المشتركة: API واحدة لكل البوتات، تُدخَل مرة واحدة ------------
SETTING_SHARED_PROVIDER = "shared_provider"
SETTING_SHARED_MODEL = "shared_model"

# -- توجيه البوت المدمج -----------------------------------------------------
# أسماء الأدوات الحقيقية كما في providers.TOOLS حرفياً (لا أداة لقطة
# شاشة للبوتات — اللقطة نقطة تحكّم هاتف في الخادم فقط).
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
    "واحفظ في النهاية بـ press_keys (ctrl+s)."
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
    "end with press_keys (ctrl+s)."
)


def orientation_text(lang: str | None = None) -> str:
    """نصّ التوجيه المدمج بلغة الواجهة الحالية (العربية عند أي تعذّر)."""
    if lang is None:
        try:
            lang = i18n.get_lang()
        except Exception:
            lang = "ar"
    return ORIENTATION_EN if lang == "en" else ORIENTATION_AR


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

    def send_message(
        self,
        bot_id: int,
        text: str,
        should_cancel=None,
        on_event=None,
        task_id: int | None = None,
    ) -> str:
        """يرسل رسالة لبوت ويعيد ردّه النهائي (مع حلقة أدوات عند الحاجة).

        المعاملات الإضافية اختيارية وسلوك غيابها هو السلوك القائم حرفياً:
        - should_cancel: دالة بلا معاملات تُستشار بين الجولات وقبل كل
          أداة؛ إن أعادت True رُفعت ChatCancelled (إلغاء تعاوني).
        - on_event: ردّ نداء (kind, text) يتلقّى أحداث التنفيذ (أدوات…)
          — يستعمله مشغّل المهام لبناء سجلّ المهمة.
        - task_id: سياق مهمة مالكة، يُحمل إلى طلبات الموافقة.
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
        # التوجيه المدمج أولاً دائماً، وتعليمات البوت الخاصة بعده.
        system_content = orientation_text()
        if bot["system_prompt"]:
            system_content += "\n\n" + bot["system_prompt"]
        messages.append({"role": "system", "content": system_content})
        messages.extend(
            self._row_to_message(r) for r in self.db.get_messages(conv_id)
        )
        self.db.add_message(conv_id, "user", text)
        messages.append({"role": "user", "content": text})

        for _round in range(MAX_TOOL_ROUNDS + 1):
            _check_cancel()
            result: ChatResult = provider.chat(messages, model, tools=TOOLS)
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
                self.db.add_message(
                    conv_id, "tool", content, tool_call_id=tc.id
                )
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": content}
                )
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
    "SETTING_SHARED_PROVIDER",
    "SETTING_SHARED_MODEL",
]
