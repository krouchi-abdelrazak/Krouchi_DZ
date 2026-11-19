"""محرّك المحادثة في Krouchi_DZ — مستقل عن أي واجهة (تقوده واجهة الخطوة 2).

يربط: قاعدة البيانات المحلية، ملف إعدادات المزوّدين، مخزن الأسرار،
ووسيط الموافقات. إرسال رسالة لبوت يحفظ الذاكرة لكل بوت في SQLite،
وإذا طلب النموذج أدوات (read_file / write_file / run_command) نُفّذت
عبر الوسيط فقط، وأُعيدت نتائجها للنموذج ليكمل ردّه.

ونقطة الدخول الأولى لإدخال API هي add_api(base_url, api_key):
أي عنوان + أي مفتاح، فيسجّل المزوّد ويكتشف نماذجه بنفسه (discovery.py).
"""

from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

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
        # نقل GET لاكتشاف النماذج (قابل للحقن في الاختبارات — بلا شبكة).
        self.get_transport = get_transport
        self._provider_cache: dict[str, object] = {}

    # -- إدارة البوتات والمفاتيح ------------------------------------------
    def create_bot(self, name: str, provider_name: str, **kwargs) -> int:
        if provider_name not in self.providers:
            raise ValueError(f"مزوّد غير معروف: {provider_name}")
        return self.db.create_bot(name, provider_name, **kwargs)

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
        cfg = self.providers[bot["provider_name"]]
        model = bot["model"] or cfg.default_model
        provider = self._get_provider(bot["provider_name"])
        conv_id = self.db.get_or_create_conversation(bot_id)

        def _check_cancel() -> None:
            if should_cancel is not None and should_cancel():
                raise ChatCancelled("أُلغيت المحادثة بطلب الإلغاء")

        messages: list[dict] = []
        if bot["system_prompt"]:
            messages.append({"role": "system", "content": bot["system_prompt"]})
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
        decision = self.broker.authorize(bot, action, params, task_id=task_id)
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
    def _do_run_command(params: dict) -> str:
        command = params["command"]
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
__all__ = ["ChatEngine", "ChatCancelled", "default_data_dir", "MAX_TOOL_ROUNDS"]
