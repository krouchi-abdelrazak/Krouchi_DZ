"""تعدّد لغات الواجهة في Krouchi_DZ — العربية والإنجليزية فقط.

جدول نصوص واحد {لغة: {مفتاح: نصّ}} وحالة لغة حالية على مستوى الوحدة:
t(key) يعيد نصّ اللغة الحالية، ويتراجع إلى العربية عند غياب المفتاح،
ثم إلى المفتاح نفسه أخيراً. الاختيار يُحفَظ في جدول إعدادات قاعدة
البيانات (المفتاح ui_lang) وافتراضيه العربية. العربية وحدها RTL.

النصوص العربية هنا هي نصوص الواجهة الأصلية حرفياً — لم تتغيّر كلمة
واحدة منها؛ الإنجليزية ترجمة واجهة مهنية موجزة لها.
"""

from __future__ import annotations

SUPPORTED_LANGS = ("ar", "en")
DEFAULT_LANG = "ar"
SETTING_KEY = "ui_lang"

# أسماء اللغات كما تظهر في منتقي اللغة (بأسمائها الذاتية دائماً).
LANG_NAMES = {"ar": "العربية", "en": "English"}

STRINGS: dict[str, dict[str, str]] = {
    "ar": {
        # -- عام ----------------------------------------------------------------
        "common.allow": "موافقة",
        "common.deny": "رفض",
        "common.cancel": "إلغاء",
        "common.save": "حفظ",
        "common.refresh": "تحديث",
        "common.err_unexpected": "خطأ غير متوقع: {error}",
        # -- أنماط الموافقة والإجراءات والقرارات ----------------------------------
        "mode.ask": "اسأل",
        "mode.full": "كامل",
        "mode.readonly": "قراءة فقط",
        "action.read_file": "قراءة ملف",
        "action.write_file": "كتابة ملف",
        "action.run_command": "تشغيل أمر",
        "decision.allowed": "سماح ✓",
        "decision.denied": "رفض ✗",
        # -- أخطاء المحرّك كما تعرضها الواجهة --------------------------------------
        "err.job_timeout": "انتهت مهلة مهمة المحرّك",
        "err.engine_slow": "تأخّر إنشاء المحرّك",
        "err.engine_start_failed": "تعذّر بدء المحرّك: {error}",
        # -- بطاقة الموافقة ---------------------------------------------------------
        "approval.title": "طلب موافقة — Krouchi_DZ",
        "approval.asks": "البوت «{bot}» يطلب إذناً:",
        "approval.action": "الإجراء: {action}",
        "approval.countdown": "يُرفض تلقائياً بعد {seconds} ثانية إن لم تُجب",
        # -- شاشة إدخال API ---------------------------------------------------------
        "addapi.title": "إدخال API — Krouchi_DZ",
        "addapi.providers": "المزوّدون المسجّلون:",
        "addapi.fetch_selected": "جلب نماذج المحدّد",
        "addapi.refresh_list": "تحديث القائمة",
        "addapi.name": "الاسم (اختياري):",
        "addapi.base_url": "عنوان الأساس (Base URL):",
        "addapi.key": "مفتاح API:",
        "addapi.fetch": "اجلب النماذج",
        "addapi.models": "النماذج المكتشفة:",
        "addapi.err_providers": "خطأ في قراءة المزوّدين: {error}",
        "addapi.verified": "مُتحقَّق ✓",
        "addapi.unverified": "غير مُتحقَّق ⚠",
        "addapi.key_saved": "مفتاح محفوظ",
        "addapi.no_key": "بلا مفتاح",
        "addapi.connecting": "جارٍ الاتصال بالمزوّد وجلب النماذج…",
        "addapi.success": "تمّ بنجاح: «{provider}» — {count} نموذجاً متاحاً",
        "addapi.from_cache": " (من الكاش)",
        "addapi.need_fields": "أدخل عنوان الأساس ومفتاح API أولاً",
        "addapi.need_selection": "اختر مزوّداً من القائمة أولاً",
        # -- نافذة البوت --------------------------------------------------------------
        "bot.new_title": "بوت جديد",
        "bot.edit_title": "تعديل بوت",
        "bot.name": "اسم البوت:",
        "bot.provider": "المزوّد:",
        "bot.model": "النموذج:",
        "bot.mode": "نمط الموافقة:",
        "bot.prompt": "تعليمات النظام:",
        "bot.loading": "جارٍ تحميل المزوّدين…",
        "bot.err_load": "خطأ في تحميل المزوّدين: {error}",
        "bot.saving": "جارٍ الحفظ…",
        "bot.err_save": "خطأ في الحفظ: {error}",
        "bot.need_name": "أدخل اسم البوت",
        "bot.need_provider": "اختر مزوّداً — أو أضف واحداً من «إدخال API»",
        # -- سجلّ التدقيق ---------------------------------------------------------------
        "audit.title": "سجلّ التدقيق — Krouchi_DZ",
        "audit.col_time": "الوقت",
        "audit.col_bot": "البوت",
        "audit.col_action": "الإجراء",
        "audit.col_decision": "القرار",
        "audit.col_reason": "السبب",
        # -- ربط الهاتف -------------------------------------------------------------------
        "phone.title": "ربط الهاتف — Krouchi_DZ",
        "phone.heading": "ربط الهاتف بالحاسوب",
        "phone.desc": "شغّل الخادم، ثم في تطبيق الهاتف أدخل أحد العناوين التالية ورمز الربط — فيتصل الهاتف ببوتات هذا الحاسوب ويحادثها من هنا، وطلبات الموافقة تظهر على الحاسوب وعلى الهاتف معاً.",
        "phone.token_label": "رمز الربط (أدخله في الهاتف كما هو):",
        "phone.stop": "إيقاف الخادم",
        "phone.regen": "رمز ربط جديد",
        "phone.start": "تشغيل الخادم",
        "phone.autostart": "تشغيل الخادم تلقائياً عند بدء البرنامج",
        "phone.warning": "تنبيه: رمز الربط سرّ — من يملكه على شبكتك المحلية يستطيع محادثة بوتاتك وطلب موافقاتك. لا تشاركه إلا مع هاتفك.",
        "phone.status_running": "● الخادم يعمل — الهاتف يستطيع الاتصال",
        "phone.addresses": "عناوين الاتصال:\n{lines}",
        "phone.no_address": "تعذّر تحديد عنوان الشبكة المحلية لهذا الحاسوب",
        "phone.status_stopped": "○ الخادم متوقّف",
        "phone.port_when_started": "المنفذ عند التشغيل: {port}",
        "phone.err_start": "تعذّر تشغيل الخادم: {error}",
        "phone.err_regen": "تعذّر تجديد الرمز: {error}",
        "phone.token_regenerated": "تمّ تجديد رمز الربط — حدّثه في تطبيق الهاتف",
        # -- النافذة الرئيسية ----------------------------------------------------------------
        "app.title": "Krouchi_DZ — وكيلك الشخصي المحلي",
        "app.bots": "البوتات",
        "app.new_bot": "➕ بوت جديد",
        "app.edit_bot": "✏️ تعديل البوت",
        "app.add_api": "🔑 إدخال API",
        "app.audit": "📜 سجلّ التدقيق",
        "app.phone_link": "📱 ربط الهاتف",
        "app.language": "اللغة",
        "app.choose_bot": "اختر بوتاً من القائمة أو أنشئ واحداً",
        "app.send": "إرسال",
        "app.err_bots": "خطأ في قراءة البوتات: {error}",
        "app.header_bot": "{avatar} {name} — {provider} / {model} — الموافقة: {mode}",
        "app.default_model": "افتراضي",
        "app.you": "🧑 أنت",
        "app.bot_requested": "🛠 طلب البوت: {names}",
        "app.list_sep": "، ",
        "app.tool_result": "نتيجة أداة: {text}",
        "app.working": "⏳ البوت يعمل…",
        "app.err_generic": "خطأ: {error}",
        "app.need_bot": "اختر بوتاً أولاً — أو أنشئ بوتاً جديداً",
        "app.need_bot_edit": "اختر بوتاً من القائمة لتعديله",
        "app.no_server": "خادم ربط الهاتف غير مهيّأ في هذه الجلسة",
    },
    "en": {
        # -- Common ----------------------------------------------------------------
        "common.allow": "Approve",
        "common.deny": "Deny",
        "common.cancel": "Cancel",
        "common.save": "Save",
        "common.refresh": "Refresh",
        "common.err_unexpected": "Unexpected error: {error}",
        # -- Approval modes, actions, decisions --------------------------------------
        "mode.ask": "Ask",
        "mode.full": "Full",
        "mode.readonly": "Read-only",
        "action.read_file": "Read file",
        "action.write_file": "Write file",
        "action.run_command": "Run command",
        "decision.allowed": "Allowed ✓",
        "decision.denied": "Denied ✗",
        # -- Engine errors as shown by the UI ------------------------------------------
        "err.job_timeout": "Engine task timed out",
        "err.engine_slow": "Engine creation took too long",
        "err.engine_start_failed": "Could not start the engine: {error}",
        # -- Approval card ---------------------------------------------------------------
        "approval.title": "Approval request — Krouchi_DZ",
        "approval.asks": "The bot “{bot}” requests permission:",
        "approval.action": "Action: {action}",
        "approval.countdown": "Automatically denied in {seconds} seconds if you don't answer",
        # -- Add API screen ----------------------------------------------------------------
        "addapi.title": "Add API — Krouchi_DZ",
        "addapi.providers": "Registered providers:",
        "addapi.fetch_selected": "Fetch selected models",
        "addapi.refresh_list": "Refresh list",
        "addapi.name": "Name (optional):",
        "addapi.base_url": "Base URL:",
        "addapi.key": "API key:",
        "addapi.fetch": "Fetch models",
        "addapi.models": "Discovered models:",
        "addapi.err_providers": "Error reading providers: {error}",
        "addapi.verified": "Verified ✓",
        "addapi.unverified": "Not verified ⚠",
        "addapi.key_saved": "Key saved",
        "addapi.no_key": "No key",
        "addapi.connecting": "Contacting the provider and fetching models…",
        "addapi.success": "Success: “{provider}” — {count} models available",
        "addapi.from_cache": " (from cache)",
        "addapi.need_fields": "Enter the base URL and the API key first",
        "addapi.need_selection": "Select a provider from the list first",
        # -- Bot dialog ---------------------------------------------------------------------
        "bot.new_title": "New bot",
        "bot.edit_title": "Edit bot",
        "bot.name": "Bot name:",
        "bot.provider": "Provider:",
        "bot.model": "Model:",
        "bot.mode": "Approval mode:",
        "bot.prompt": "System instructions:",
        "bot.loading": "Loading providers…",
        "bot.err_load": "Error loading providers: {error}",
        "bot.saving": "Saving…",
        "bot.err_save": "Error saving: {error}",
        "bot.need_name": "Enter the bot name",
        "bot.need_provider": "Choose a provider — or add one from “Add API”",
        # -- Audit log -------------------------------------------------------------------------
        "audit.title": "Audit log — Krouchi_DZ",
        "audit.col_time": "Time",
        "audit.col_bot": "Bot",
        "audit.col_action": "Action",
        "audit.col_decision": "Decision",
        "audit.col_reason": "Reason",
        # -- Phone link ---------------------------------------------------------------------------
        "phone.title": "Phone link — Krouchi_DZ",
        "phone.heading": "Link the phone to this computer",
        "phone.desc": "Start the server, then in the phone app enter one of the addresses below and the pairing token — the phone then connects to this computer's bots and chats with them here, and approval requests appear on the computer and the phone together.",
        "phone.token_label": "Pairing token (enter it in the phone exactly as shown):",
        "phone.stop": "Stop server",
        "phone.regen": "New pairing token",
        "phone.start": "Start server",
        "phone.autostart": "Start the server automatically when the program starts",
        "phone.warning": "Warning: the pairing token is a secret — anyone on your local network who has it can chat with your bots and request your approvals. Share it only with your phone.",
        "phone.status_running": "● Server running — the phone can connect",
        "phone.addresses": "Connection addresses:\n{lines}",
        "phone.no_address": "Could not determine this computer's local network address",
        "phone.status_stopped": "○ Server stopped",
        "phone.port_when_started": "Port when started: {port}",
        "phone.err_start": "Could not start the server: {error}",
        "phone.err_regen": "Could not regenerate the token: {error}",
        "phone.token_regenerated": "Pairing token regenerated — update it in the phone app",
        # -- Main window ------------------------------------------------------------------------------
        "app.title": "Krouchi_DZ — your local personal agent",
        "app.bots": "Bots",
        "app.new_bot": "➕ New bot",
        "app.edit_bot": "✏️ Edit bot",
        "app.add_api": "🔑 Add API",
        "app.audit": "📜 Audit log",
        "app.phone_link": "📱 Phone link",
        "app.language": "Language",
        "app.choose_bot": "Choose a bot from the list or create one",
        "app.send": "Send",
        "app.err_bots": "Error reading bots: {error}",
        "app.header_bot": "{avatar} {name} — {provider} / {model} — Approval: {mode}",
        "app.default_model": "default",
        "app.you": "🧑 You",
        "app.bot_requested": "🛠 The bot requested: {names}",
        "app.list_sep": ", ",
        "app.tool_result": "Tool result: {text}",
        "app.working": "⏳ The bot is working…",
        "app.err_generic": "Error: {error}",
        "app.need_bot": "Choose a bot first — or create a new one",
        "app.need_bot_edit": "Choose a bot from the list to edit it",
        "app.no_server": "The phone-link server is not set up in this session",
    },
}


_current: str = DEFAULT_LANG


def get_lang() -> str:
    """اللغة الحالية للواجهة ('ar' افتراضياً)."""
    return _current


def set_lang(lang: str) -> str:
    """يضبط اللغة الحالية؛ قيمة غير مدعومة تتراجع إلى الافتراضية."""
    global _current
    _current = lang if lang in STRINGS else DEFAULT_LANG
    return _current


def is_rtl() -> bool:
    """العربية وحدها اتجاهها من اليمين إلى اليسار."""
    return _current == "ar"


def has(key: str) -> bool:
    """هل للمفتاح نصّ في اللغة الحالية أو في العربية؟"""
    return key in STRINGS[_current] or key in STRINGS[DEFAULT_LANG]


def t(key: str, **fmt) -> str:
    """نصّ المفتاح باللغة الحالية (تراجع: العربية، ثم المفتاح نفسه).

    وسائط fmt تُمرَّر إلى str.format — النصوص ذات العناصر النائبة
    مثل {error} و{bot} تُملأ منها.
    """
    text = STRINGS[_current].get(key)
    if text is None:
        text = STRINGS[DEFAULT_LANG].get(key, key)
    if fmt:
        text = text.format(**fmt)
    return text


def load_lang(db) -> str:
    """يقرأ اللغة المحفوظة من إعدادات قاعدة البيانات ويجعلها الحالية."""
    stored = db.get_setting(SETTING_KEY, DEFAULT_LANG)
    return set_lang(stored)


def save_lang(db, lang: str) -> str:
    """يحفظ اللغة في إعدادات قاعدة البيانات ويجعلها الحالية."""
    applied = set_lang(lang)
    db.set_setting(SETTING_KEY, applied)
    return applied
