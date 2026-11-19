/* Krouchi_DZ — تطبيق الهاتف (شيفرة أصلية).
 *
 * منطق اكتشاف المزوّدين والمحادثة مرآة لسلوك نسخة سطح المكتب
 * (krouchi_dz/discovery.py): تطبيع العنوان، ثم GET {base}/models
 * بالمفتاح لجلب النماذج، وأخطاء مميّزة لكل فشل.
 * النسخة 2.0: وضع مرافق للحاسوب (خادم مكتبي + رمز اقتران).
 * النسخة 3.0: واجهة بلغتين (العربية / English) مع مفتاح لغة
 * محفوظ في التخزين المحلي — كل النصوص تمرّ عبر جدول STRINGS
 * ودالة t() وقت العرض.
 * نسخة المتصفح (PWA): نفس الشيفرة؛ عند غياب الجسر الأصيل يعمل
 * نقل fetch بنفس عقد النتائج {status, text, error} وبنفس المهل.
 */
'use strict';

/* ================= تعدّد اللغات: جدول النصوص =================
 * العربية هي الأصل (نصوص الواجهة كما كانت)، والإنجليزية ترجمة
 * طبيعية كاملة. كل مفتاح موجود في اللغتين بنفس الاسم. */
var STRINGS = {
  ar: {
    app_tagline: 'وكيلك الشخصي على الهاتف — بمفاتيحك أنت',
    tab_api: '🔑 إدخال API',
    tab_bots: '🤖 البوتات',
    tab_chat: '💬 المحادثة',
    tab_pc: '🖥️ الحاسوب',
    tab_about: 'ℹ️ حول',
    api_title: 'إدخال API — أي مفتاح وأي عنوان',
    label_base_url: 'عنوان الأساس (Base URL)',
    label_api_key: 'مفتاح API',
    label_provider_name: 'اسم المزوّد (اختياري — يُشتق من الخادم إن تُرك)',
    btn_fetch_models: 'اجلب النماذج',
    providers_registered: 'المزوّدون المسجّلون',
    bot_new: 'بوت جديد',
    label_bot_name: 'اسم البوت',
    ph_bot_name: 'مساعدي',
    label_provider: 'المزوّد',
    label_model: 'النموذج (اختر من المكتشفة أو اكتب)',
    label_system: 'تعليمات النظام (اختيارية)',
    ph_system: 'أنت مساعد دقيق يجيب بالعربية…',
    btn_create_bot: 'إنشاء البوت',
    bots_mine: 'بوتاتي',
    chat_title: 'المحادثة',
    label_bot: 'البوت',
    ph_message: 'اكتب رسالتك…',
    btn_send: 'إرسال',
    btn_clear_chat: 'مسح المحادثة',
    pc_title: 'الاتصال بالحاسوب',
    pc_intro: 'اربط الهاتف ببرنامج Krouchi_DZ على حاسوبك (على نفس الشبكة) لاستعمال بوتات الحاسوب من الهاتف، والموافقة على طلبات تنفيذه أو رفضها من هاتفك.',
    label_pc_host: 'عنوان الحاسوب (IP أو اسم المضيف)',
    label_pc_port: 'المنفذ',
    label_pc_token: 'رمز الاقتران',
    ph_pc_token: 'رمز الاقتران من الحاسوب',
    btn_connect: 'اتصال',
    pc_pending_approvals: 'الموافقات المعلّقة',
    pc_approvals_note: 'حين يطلب بوت على الحاسوب تنفيذ إجراء، يظهر طلبه هنا لتُوافق عليه أو ترفضه — وعدم الجواب يبقيه معلّقاً على الحاسوب.',
    pc_bots_title: 'بوتات الحاسوب',
    pc_chat_title: 'محادثة الحاسوب',
    btn_pc_back: 'عودة إلى بوتات الحاسوب',
    about_title: 'حول Krouchi_DZ',
    about_author: 'تأليف: كروشي عبد الرزاق',
    about_p1: 'الإصدار 3.0 — رفيق الهاتف لبرنامج Krouchi_DZ المكتبي، بشيفرة أصلية مكتوبة من الصفر.',
    about_p2: 'وضعان: <b>مستقل على الهاتف</b> (إدخال API واكتشاف النماذج والمحادثة — لا أدوات ملفات ولا تشغيل أوامر على الهاتف)، و<b>مرافق للحاسوب</b> من تبويب «الحاسوب»: محادثة عبر بوتات الحاسوب، والموافقة على طلبات تنفيذه أو رفضها من هاتفك.',
    about_p3: 'مفاتيحك ومحادثاتك محفوظة في تخزين هذا التطبيق الخاص على هاتفك، ولا تغادر بياناتك الجهاز إلا إلى مزوّد النماذج الذي تختاره وبمفتاحك — أو إلى حاسوبك أنت عند استعمال الوضع المرافق.',
    label_language: 'اللغة',
    err_bad_url: 'العنوان غير صالح — تأكد أنه يبدأ بـ http:// أو https:// ويحمل اسم خادم',
    err_unreachable: 'تعذّر الوصول إلى الخادم — تحقق من العنوان ومن اتصال الإنترنت',
    err_auth: 'رفض المزوّد المفتاح (خطأ مصادقة 401/403) — تحقق من صحة مفتاح API',
    err_not_json: 'ردّ الخادم ليس JSON — غالباً العنوان ليس عنوان API صحيحاً',
    err_bad_shape: 'وصل ردّ من الخادم، لكنه لا يحمل قائمة نماذج بالشكل المتوقع',
    err_empty: 'اتصلنا بالمزوّد بنجاح، لكنه لم يُعد أي نموذج متاحاً لهذا المفتاح',
    err_no_key: 'لا يوجد مفتاح محفوظ لهذا المزوّد — أضف مفتاح API أولاً',
    err_chat_shape: 'وصل ردّ من الخادم، لكنه لا يحمل نصّ محادثة بالشكل المتوقع',
    err_http: 'أعاد الخادم خطأ HTTP {status} — راجع العنوان أو حالة الخدمة',
    err_pc_unreachable: 'تعذّر الوصول إلى الحاسوب — تحقق من العنوان والمنفذ، وأن الحاسوب مشغّل وعلى نفس الشبكة',
    err_pc_token: 'رفض الحاسوب رمز الاقتران (401/403) — تحقق من الرمز المدخل',
    err_pc_notapp: 'الخادم الذي ردّ على هذا العنوان ليس Krouchi_DZ',
    err_pc_shape: 'وصل ردّ من الحاسوب، لكنه ليس بالشكل المتوقع',
    err_pc_http: 'أعاد الحاسوب خطأ HTTP {status}',
    api_connecting: 'جارٍ الاتصال بالمزوّد وجلب النماذج…',
    api_success: 'تمّ بنجاح: {name} — {count} نموذجاً متاحاً',
    providers_none: 'لا مزوّدين بعد — أضف أول API من النموذج أعلاه.',
    badge_verified: 'مُتحقَّق ✓',
    badge_unverified: 'غير مُتحقَّق',
    models_count: '{count} نموذجاً',
    btn_delete_provider: 'حذف المزوّد',
    toast_provider_deleted: 'حُذف المزوّد',
    provider_unverified_suffix: ' (غير مُتحقَّق)',
    bot_err_name: 'أدخل اسماً للبوت',
    bot_err_provider: 'أضف مزوّداً أولاً من تبويب «إدخال API»',
    bot_err_model: 'اختر نموذجاً أو اكتبه',
    bot_created: 'أُنشئ البوت «{name}» بنجاح',
    bots_none: 'لا بوتات بعد — أنشئ أول بوت من النموذج أعلاه.',
    btn_chat_with: '💬 محادثة',
    btn_delete: 'حذف',
    unknown_mark: '؟',
    toast_bot_deleted: 'حُذف البوت',
    chat_no_bot: 'لا بوت محدّد — أنشئ بوتاً من تبويب «البوتات».',
    chat_empty: 'ابدأ المحادثة بكتابة رسالة.',
    you: 'أنت',
    chat_writing: '⏳ يكتب…',
    chat_provider_gone: 'مزوّد هذا البوت محذوف — أعد إضافته من تبويب «إدخال API»',
    toast_chat_cleared: 'مُسحت محادثة «{name}»',
    mode_ask: 'يسأل قبل التنفيذ',
    mode_full: 'صلاحيات كاملة',
    mode_readonly: 'قراءة فقط',
    pc_err_host: 'أدخل عنوان الحاسوب أولاً (مثال: 192.168.1.10)',
    pc_err_token: 'أدخل رمز الاقتران الذي يعرضه الحاسوب',
    pc_connecting_btn: 'جارٍ الاتصال…',
    pc_testing: 'جارٍ اختبار الاتصال بالحاسوب…',
    pc_connected: 'متصل بالحاسوب ✓ — Krouchi_DZ',
    pc_connected_version: ' (الإصدار {version})',
    pc_bots_none: 'لا بوتات على الحاسوب بعد.',
    pc_mode_line: 'الوضع: {mode}',
    btn_pc_chat: '💬 محادثة عبر الحاسوب',
    pc_bot_fallback_name: 'بوت الحاسوب',
    pc_chat_with: 'محادثة: {name} (على الحاسوب)',
    pc_chat_pick: 'اختر بوتاً من قائمة بوتات الحاسوب.',
    pc_chat_sending: '⏳ …',
    approvals_waiting: '{count} بانتظار قرارك',
    approvals_none: 'لا طلبات معلّقة الآن.',
    approval_request_from: '🔔 طلب تنفيذ — {name}',
    approval_bot_fallback: 'بوت',
    approval_tool: 'الأداة: {tool}',
    btn_approve: '✅ موافقة',
    btn_deny: '⛔ رفض',
    toast_approved: 'أُرسلت الموافقة إلى الحاسوب',
    toast_denied: 'أُرسل الرفض إلى الحاسوب'
  },
  en: {
    app_tagline: 'Your personal agent on your phone — with your own keys',
    tab_api: '🔑 Add API',
    tab_bots: '🤖 Bots',
    tab_chat: '💬 Chat',
    tab_pc: '🖥️ Computer',
    tab_about: 'ℹ️ About',
    api_title: 'Add API — any key, any URL',
    label_base_url: 'Base URL',
    label_api_key: 'API Key',
    label_provider_name: 'Provider name (optional — derived from the host if left blank)',
    btn_fetch_models: 'Fetch models',
    providers_registered: 'Registered providers',
    bot_new: 'New bot',
    label_bot_name: 'Bot name',
    ph_bot_name: 'My assistant',
    label_provider: 'Provider',
    label_model: 'Model (pick from the discovered ones or type one)',
    label_system: 'System instructions (optional)',
    ph_system: 'You are a precise, helpful assistant…',
    btn_create_bot: 'Create bot',
    bots_mine: 'My bots',
    chat_title: 'Chat',
    label_bot: 'Bot',
    ph_message: 'Type your message…',
    btn_send: 'Send',
    btn_clear_chat: 'Clear conversation',
    pc_title: 'Connect to a computer',
    pc_intro: 'Link your phone to the Krouchi_DZ program on your computer (on the same network) to use the computer\'s bots from your phone, and to approve or deny its execution requests from your phone.',
    label_pc_host: 'Computer address (IP or hostname)',
    label_pc_port: 'Port',
    label_pc_token: 'Pairing token',
    ph_pc_token: 'Pairing token from the computer',
    btn_connect: 'Connect',
    pc_pending_approvals: 'Pending approvals',
    pc_approvals_note: 'When a bot on the computer asks to execute an action, its request appears here for you to approve or deny — no answer leaves it pending on the computer.',
    pc_bots_title: 'Computer bots',
    pc_chat_title: 'Computer chat',
    btn_pc_back: 'Back to computer bots',
    about_title: 'About Krouchi_DZ',
    about_author: 'By Krouchi Abderrazak',
    about_p1: 'Version 3.0 — the phone companion to the Krouchi_DZ desktop program, with original code written from scratch.',
    about_p2: 'Two modes: <b>standalone on the phone</b> (API entry, model discovery and chat — no file tools and no command execution on the phone), and a <b>computer companion</b> from the "Computer" tab: chat through the computer\'s bots, and approve or deny its execution requests from your phone.',
    about_p3: 'Your keys and conversations are stored in this app\'s private storage on your phone, and your data leaves the device only to the model provider you choose, with your own key — or to your own computer when using the companion mode.',
    label_language: 'Language',
    err_bad_url: 'Invalid URL — make sure it starts with http:// or https:// and contains a host name',
    err_unreachable: 'Could not reach the server — check the URL and your internet connection',
    err_auth: 'The provider rejected the key (authentication error 401/403) — check your API key',
    err_not_json: 'The server\'s reply is not JSON — the URL is probably not a valid API endpoint',
    err_bad_shape: 'The server replied, but without a model list in the expected shape',
    err_empty: 'Connected to the provider successfully, but it returned no models available for this key',
    err_no_key: 'No saved key for this provider — add an API key first',
    err_chat_shape: 'The server replied, but without chat text in the expected shape',
    err_http: 'The server returned HTTP error {status} — check the URL or the service status',
    err_pc_unreachable: 'Could not reach the computer — check the address and port, and that the computer is on and on the same network',
    err_pc_token: 'The computer rejected the pairing token (401/403) — check the token you entered',
    err_pc_notapp: 'The server that answered at this address is not Krouchi_DZ',
    err_pc_shape: 'The computer replied, but not in the expected shape',
    err_pc_http: 'The computer returned HTTP error {status}',
    api_connecting: 'Contacting the provider and fetching models…',
    api_success: 'Success: {name} — {count} models available',
    providers_none: 'No providers yet — add your first API from the form above.',
    badge_verified: 'Verified ✓',
    badge_unverified: 'Unverified',
    models_count: '{count} models',
    btn_delete_provider: 'Delete provider',
    toast_provider_deleted: 'Provider deleted',
    provider_unverified_suffix: ' (unverified)',
    bot_err_name: 'Enter a name for the bot',
    bot_err_provider: 'Add a provider first from the "Add API" tab',
    bot_err_model: 'Pick a model or type one',
    bot_created: 'Bot "{name}" created successfully',
    bots_none: 'No bots yet — create your first bot from the form above.',
    btn_chat_with: '💬 Chat',
    btn_delete: 'Delete',
    unknown_mark: '?',
    toast_bot_deleted: 'Bot deleted',
    chat_no_bot: 'No bot selected — create a bot from the "Bots" tab.',
    chat_empty: 'Start the conversation by typing a message.',
    you: 'You',
    chat_writing: '⏳ typing…',
    chat_provider_gone: 'This bot\'s provider was deleted — re-add it from the "Add API" tab',
    toast_chat_cleared: 'Conversation with "{name}" cleared',
    mode_ask: 'Asks before executing',
    mode_full: 'Full access',
    mode_readonly: 'Read-only',
    pc_err_host: 'Enter the computer address first (e.g. 192.168.1.10)',
    pc_err_token: 'Enter the pairing token shown on the computer',
    pc_connecting_btn: 'Connecting…',
    pc_testing: 'Testing the connection to the computer…',
    pc_connected: 'Connected to the computer ✓ — Krouchi_DZ',
    pc_connected_version: ' (version {version})',
    pc_bots_none: 'No bots on the computer yet.',
    pc_mode_line: 'Mode: {mode}',
    btn_pc_chat: '💬 Chat via computer',
    pc_bot_fallback_name: 'Computer bot',
    pc_chat_with: 'Chat: {name} (on the computer)',
    pc_chat_pick: 'Pick a bot from the computer bots list.',
    pc_chat_sending: '⏳ …',
    approvals_waiting: '{count} awaiting your decision',
    approvals_none: 'No pending requests right now.',
    approval_request_from: '🔔 Execution request — {name}',
    approval_bot_fallback: 'bot',
    approval_tool: 'Tool: {tool}',
    btn_approve: '✅ Approve',
    btn_deny: '⛔ Deny',
    toast_approved: 'Approval sent to the computer',
    toast_denied: 'Denial sent to the computer'
  }
};

var SUPPORTED_LANGS = ['ar', 'en'];
var LS_LANG = 'krouchi.lang.v1';

function loadLang() {
  try {
    var v = localStorage.getItem(LS_LANG);
    return SUPPORTED_LANGS.indexOf(v) >= 0 ? v : 'ar';
  } catch (e) {
    return 'ar';
  }
}

function saveLang(lang) {
  try {
    localStorage.setItem(LS_LANG, lang);
  } catch (e) { /* تخزين محظور: نبقى على الافتراضي */ }
}

var LANG = loadLang();

function getLang() { return LANG; }

/* ترجمة مفتاح بلغة معيّنة مع إحلال {متغيرات} — احتياط: العربية ثم المفتاح */
function translate(lang, key, vars) {
  var table = STRINGS[lang] || STRINGS.ar;
  var text = table[key];
  if (text == null) text = STRINGS.ar[key];
  if (text == null) return key;
  if (vars) {
    text = text.replace(/\{(\w+)\}/g, function (m, name) {
      return vars[name] != null ? String(vars[name]) : m;
    });
  }
  return text;
}

function t(key, vars) { return translate(LANG, key, vars); }

function setLang(lang) {
  LANG = SUPPORTED_LANGS.indexOf(lang) >= 0 ? lang : 'ar';
  saveLang(LANG);
  applyLang();
  return LANG;
}

/* تطبيق اللغة على مستند: اتجاه + نصوص ثابتة (data-i18n) وHTML
 * (data-i18n-html) وتلميحات (data-i18n-ph). دالة تأخذ المستند
 * كوسيط لتبقى قابلة للاختبار خارج المتصفح. */
function localizeDocument(doc, lang) {
  var use = SUPPORTED_LANGS.indexOf(lang) >= 0 ? lang : 'ar';
  doc.documentElement.setAttribute('lang', use);
  doc.documentElement.setAttribute('dir', use === 'ar' ? 'rtl' : 'ltr');
  doc.querySelectorAll('[data-i18n]').forEach(function (node) {
    node.textContent = translate(use, node.getAttribute('data-i18n'));
  });
  doc.querySelectorAll('[data-i18n-html]').forEach(function (node) {
    node.innerHTML = translate(use, node.getAttribute('data-i18n-html'));
  });
  doc.querySelectorAll('[data-i18n-ph]').forEach(function (node) {
    node.setAttribute('placeholder', translate(use, node.getAttribute('data-i18n-ph')));
  });
}

/* ---------- رسائل الخطأ (نفس نصوص discovery.py بالعربية) ----------
 * تُبقى الثوابت العربية للتوافق، أما العرض الفعلي فيمرّ عبر t(). */
var ERR_BAD_URL = STRINGS.ar.err_bad_url;
var ERR_UNREACHABLE = STRINGS.ar.err_unreachable;
var ERR_AUTH = STRINGS.ar.err_auth;
var ERR_NOT_JSON = STRINGS.ar.err_not_json;
var ERR_BAD_SHAPE = STRINGS.ar.err_bad_shape;
var ERR_EMPTY = STRINGS.ar.err_empty;
var ERR_NO_KEY = STRINGS.ar.err_no_key;
var ERR_CHAT_SHAPE = STRINGS.ar.err_chat_shape;

function discError(kind, message) {
  var e = new Error(message);
  e.kind = kind;
  return e;
}

/* ---------- تطبيع العنوان (مرآة normalize_base_url، نوع openai) ---------- */
var VERSION_SEGMENT = /^v\d+(\.\d+)?(beta|alpha)?$/;

function normalizeBaseUrl(rawUrl) {
  var text = (rawUrl || '').trim();
  if (!text) throw discError('bad_url', t('err_bad_url'));
  if (text.indexOf('://') < 0) text = 'https://' + text;
  var parsed;
  try {
    parsed = new URL(text);
  } catch (e) {
    throw discError('bad_url', t('err_bad_url'));
  }
  if ((parsed.protocol !== 'http:' && parsed.protocol !== 'https:') || !parsed.hostname) {
    throw discError('bad_url', t('err_bad_url'));
  }
  var path = parsed.pathname.replace(/\/+$/, '');
  var suffixes = ['/chat/completions', '/models'];
  for (var i = 0; i < suffixes.length; i++) {
    if (path.endsWith(suffixes[i])) {
      path = path.slice(0, path.length - suffixes[i].length).replace(/\/+$/, '');
      break;
    }
  }
  var base = parsed.protocol + '//' + parsed.host + path;
  var lastSegment = path ? path.split('/').pop() : '';
  if (!VERSION_SEGMENT.test(lastSegment)) {
    base += '/v1';
  }
  return base;
}

/* ---------- اشتقاق اسم المزوّد من الخادم (مرآة derive_name) ---------- */
function deriveName(baseUrl) {
  var host = 'custom';
  try {
    host = (new URL(baseUrl)).hostname.toLowerCase();
  } catch (e) { /* يبقى custom */ }
  var parts = host.split('.');
  while (parts.length > 2 && ['api', 'www', 'integrate'].indexOf(parts[0]) >= 0) {
    parts.shift();
  }
  var label;
  if (parts.length >= 2) {
    label = parts[parts.length - 2];
    if (label.length < 3) label = parts.join('-');
  } else {
    label = parts[0];
  }
  label = (label || 'custom').replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
  return label || 'custom';
}

function sanitizeName(name) {
  var cleaned = String(name || '').trim().toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
  return cleaned || 'custom';
}

/* ---------- تحليل ردّ النماذج (شكل OpenAI القياسي) ---------- */
function parseModelsOpenAI(data) {
  var items = (data && typeof data === 'object') ? data.data : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_bad_shape'));
  var models = [];
  items.forEach(function (item) {
    if (item && typeof item === 'object' && item.id) {
      var id = String(item.id);
      if (models.indexOf(id) < 0) models.push(id);
    }
  });
  if (!models.length) throw discError('empty', t('err_empty'));
  return models;
}

function httpErrorFor(status) {
  if (status === 401 || status === 403) return discError('auth', t('err_auth'));
  return discError('http', t('err_http', { status: status }));
}

/* ---------- طبقة النقل: جسر Java الأصيل، وإلا fetch ---------- */
var __reqSeq = 0;
var __pending = {};

if (typeof window !== 'undefined') {
  window.__krouchiHttpDone = function (id, status, bodyB64, error) {
    var p = __pending[id];
    if (!p) return;
    delete __pending[id];
    var text = '';
    if (bodyB64) {
      try {
        text = decodeURIComponent(escape(atob(bodyB64)));
      } catch (e) {
        try { text = atob(bodyB64); } catch (e2) { text = ''; }
      }
    }
    p({ status: status, text: text, error: error || '' });
  };
}

/* نقل fetch للمتصفح: نفس عقد نتيجة الجسر {status, text, error} —
 * status=0 عند فشل شبكي أو انقضاء المهلة (error='timeout').
 * المهلة الافتراضية 90 ثانية كما في الجسر، و fetchImpl قابل
 * للحقن من الاختبارات. */
function fetchTransport(method, url, headers, body, timeoutMs, fetchImpl) {
  var impl = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
  if (!impl) {
    return Promise.resolve({ status: 0, text: '', error: 'no transport' });
  }
  var ms = timeoutMs ? timeoutMs : 90000;
  var controller = (typeof AbortController !== 'undefined')
    ? new AbortController() : null;
  var timedOut = false;
  var timer = null;
  if (controller) {
    timer = setTimeout(function () {
      timedOut = true;
      try { controller.abort(); } catch (e) { /* لا شيء */ }
    }, ms);
  }
  var opts = { method: method, headers: headers || {} };
  if (body) opts.body = body;
  if (controller) opts.signal = controller.signal;
  return impl(url, opts).then(function (r) {
    return r.text().then(function (t2) {
      if (timer) clearTimeout(timer);
      return { status: r.status, text: t2, error: '' };
    });
  }).catch(function (e) {
    if (timer) clearTimeout(timer);
    if (timedOut) return { status: 0, text: '', error: 'timeout' };
    return { status: 0, text: '', error: String(e) };
  });
}

function httpRequest(method, url, headers, body, timeoutMs) {
  return new Promise(function (resolve) {
    if (typeof window !== 'undefined' && window.KrouchiBridge && window.KrouchiBridge.http) {
      var id = 'r' + (++__reqSeq) + '_' + Date.now();
      /* مؤقّت الواجهة يفوق مهلة قراءة الجسر حتى لا يسبقها */
      var limit = timeoutMs ? timeoutMs + 20000 : 100000;
      var timer = setTimeout(function () {
        if (__pending[id]) {
          delete __pending[id];
          resolve({ status: 0, text: '', error: 'timeout' });
        }
      }, limit);
      __pending[id] = function (res) {
        clearTimeout(timer);
        resolve(res);
      };
      try {
        if (timeoutMs) {
          window.KrouchiBridge.http(id, method, url,
            headers ? JSON.stringify(headers) : '', body || '', timeoutMs);
        } else {
          window.KrouchiBridge.http(id, method, url,
            headers ? JSON.stringify(headers) : '', body || '');
        }
      } catch (e) {
        clearTimeout(timer);
        delete __pending[id];
        resolve({ status: 0, text: '', error: String(e) });
      }
    } else if (typeof fetch !== 'undefined') {
      fetchTransport(method, url, headers, body, timeoutMs).then(resolve);
    } else {
      resolve({ status: 0, text: '', error: 'no transport' });
    }
  });
}

/* ---------- اكتشاف النماذج: GET {base}/models ---------- */
function discoverModels(baseUrl, apiKey) {
  var url = baseUrl.replace(/\/+$/, '') + '/models';
  return httpRequest('GET', url, { 'Authorization': 'Bearer ' + apiKey }, '')
    .then(function (res) {
      if (res.status === 0) {
        throw discError('unreachable', t('err_unreachable') + (res.error ? ' (' + res.error + ')' : ''));
      }
      if (res.status < 200 || res.status >= 300) throw httpErrorFor(res.status);
      var data;
      try {
        data = JSON.parse(res.text);
      } catch (e) {
        throw discError('not_json', t('err_not_json'));
      }
      if (!data || typeof data !== 'object') throw discError('bad_shape', t('err_bad_shape'));
      return parseModelsOpenAI(data);
    });
}

/* ---------- المحادثة: POST {base}/chat/completions ---------- */
function buildChatBody(model, messages) {
  return JSON.stringify({ model: model, messages: messages });
}

function parseChatReply(data) {
  var choices = (data && typeof data === 'object') ? data.choices : null;
  if (!Array.isArray(choices) || !choices.length
      || !choices[0].message || typeof choices[0].message.content !== 'string') {
    throw discError('bad_shape', t('err_chat_shape'));
  }
  return choices[0].message.content;
}

function sendChat(baseUrl, apiKey, model, messages) {
  var url = baseUrl.replace(/\/+$/, '') + '/chat/completions';
  var headers = {
    'Authorization': 'Bearer ' + apiKey,
    'Content-Type': 'application/json'
  };
  return httpRequest('POST', url, headers, buildChatBody(model, messages))
    .then(function (res) {
      if (res.status === 0) {
        throw discError('unreachable', t('err_unreachable') + (res.error ? ' (' + res.error + ')' : ''));
      }
      if (res.status < 200 || res.status >= 300) throw httpErrorFor(res.status);
      var data;
      try {
        data = JSON.parse(res.text);
      } catch (e) {
        throw discError('not_json', t('err_not_json'));
      }
      return parseChatReply(data);
    });
}

/* ---------- التخزين المحلي (تخزين التطبيق الخاص عبر DOM Storage) ---------- */
var LS_PROVIDERS = 'krouchi.providers.v1';
var LS_BOTS = 'krouchi.bots.v1';
var LS_CHATS = 'krouchi.chats.v1';

function lsRead(key, fallback) {
  try {
    var raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
}

function lsWrite(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) { /* تخزين ممتلئ/محظور: نتجاهل بصمت */ }
}

function loadProviders() { return lsRead(LS_PROVIDERS, []); }
function saveProviders(list) { lsWrite(LS_PROVIDERS, list); }
function loadBots() { return lsRead(LS_BOTS, []); }
function saveBots(list) { lsWrite(LS_BOTS, list); }
function loadChats() { return lsRead(LS_CHATS, {}); }
function saveChats(map) { lsWrite(LS_CHATS, map); }

function upsertProvider(entry) {
  var list = loadProviders();
  for (var i = 0; i < list.length; i++) {
    if (list[i].base === entry.base) {
      entry.id = list[i].id;
      list[i] = entry;
      saveProviders(list);
      return entry;
    }
  }
  entry.id = 'p' + Date.now() + '_' + Math.floor(Math.random() * 1e6);
  list.push(entry);
  saveProviders(list);
  return entry;
}

function findProvider(id) {
  var list = loadProviders();
  for (var i = 0; i < list.length; i++) {
    if (list[i].id === id) return list[i];
  }
  return null;
}

/* ================= الوضع المرافق: الاتصال بالحاسوب =================
 * العقد الثابت مع خادم Krouchi_DZ المكتبي:
 *   http://<pc>:8765  +  ترويسة X-Krouchi-Token على كل طلب
 *   GET  /api/ping                    → {ok, app:"Krouchi_DZ", version}
 *   GET  /api/bots                    → {bots:[{id,name,provider,model,mode}]}
 *   GET  /api/history?bot=<id>        → {messages:[...]}
 *   POST /api/chat {bot_id,text}      → {reply}  (قد ينتظر موافقة ~120s)
 *   GET  /api/approvals               → {pending:[{id,bot_name,tool,summary,created}]}
 *   POST /api/approvals/<id> {decision:"approve"|"deny"}
 */
var LS_PC = 'krouchi.pc.v1';
var PC_DEFAULT_PORT = 8765;
/* مهلة قراءة محادثة الحاسوب: الردّ قد ينتظر موافقة على الحاسوب */
var PC_CHAT_TIMEOUT_MS = 170000;

var ERR_PC_UNREACHABLE = STRINGS.ar.err_pc_unreachable;
var ERR_PC_TOKEN = STRINGS.ar.err_pc_token;
var ERR_PC_NOTAPP = STRINGS.ar.err_pc_notapp;
var ERR_PC_SHAPE = STRINGS.ar.err_pc_shape;

function defaultPcConfig() {
  return { host: '', port: PC_DEFAULT_PORT, token: '' };
}

function normalizePcConfig(cfg) {
  cfg = cfg || {};
  var port = parseInt(cfg.port, 10);
  if (!port || port < 1 || port > 65535) port = PC_DEFAULT_PORT;
  return {
    host: String(cfg.host == null ? '' : cfg.host).trim(),
    port: port,
    token: String(cfg.token == null ? '' : cfg.token).trim()
  };
}

function loadPcConfig() {
  return normalizePcConfig(lsRead(LS_PC, defaultPcConfig()));
}

function savePcConfig(cfg) {
  var clean = normalizePcConfig(cfg);
  lsWrite(LS_PC, clean);
  return clean;
}

/* عنوان الأساس للخادم المكتبي: يقبل IP مجرداً أو رابطاً ملصوقاً كاملاً */
function pcBaseUrl(cfg) {
  cfg = normalizePcConfig(cfg);
  if (!cfg.host) throw discError('bad_url', t('err_bad_url'));
  var text = cfg.host;
  if (text.indexOf('://') < 0) text = 'http://' + text;
  var parsed;
  try {
    parsed = new URL(text);
  } catch (e) {
    throw discError('bad_url', t('err_bad_url'));
  }
  if (!parsed.hostname) throw discError('bad_url', t('err_bad_url'));
  var port = cfg.port;
  if (parsed.port) {
    var pasted = parseInt(parsed.port, 10);
    if (pasted >= 1 && pasted <= 65535) port = pasted;
  }
  return 'http://' + parsed.hostname + ':' + port;
}

function pcHeaders(cfg) {
  return { 'X-Krouchi-Token': normalizePcConfig(cfg).token };
}

/* بناء وصف الطلب (رابط + ترويسات + جسم) — دالة نقية قابلة للاختبار */
function buildPcRequest(cfg, method, path, bodyObj) {
  var headers = pcHeaders(cfg);
  var body = '';
  if (bodyObj != null) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(bodyObj);
  }
  return { method: method, url: pcBaseUrl(cfg) + path, headers: headers, body: body };
}

function pcChatBody(botId, text) {
  /* معرّف البوت قد يصل نصّاً من خاصية HTML (getAttribute) — يُحوَّل إلى رقم */
  var id = botId;
  if (typeof id === 'string' && /^-?\d+$/.test(id.trim())) id = Number(id);
  return { bot_id: id, text: text };
}

function pcDecisionBody(decision) {
  return { decision: decision === 'approve' ? 'approve' : 'deny' };
}

/* طلب إلى الحاسوب: يحوّل الردّ JSON أو يرمي خطأ مميّزاً بلغة الواجهة.
 * transport قابل للحقن (اختبارات Node) — الافتراضي httpRequest. */
function pcRequest(cfg, method, path, bodyObj, timeoutMs, transport) {
  var send = transport || httpRequest;
  var req = buildPcRequest(cfg, method, path, bodyObj);
  return send(req.method, req.url, req.headers, req.body, timeoutMs)
    .then(function (res) {
      if (res.status === 0) {
        throw discError('unreachable',
          t('err_pc_unreachable') + (res.error ? ' (' + res.error + ')' : ''));
      }
      if (res.status === 401 || res.status === 403) {
        throw discError('auth', t('err_pc_token'));
      }
      if (res.status < 200 || res.status >= 300) {
        throw discError('http', t('err_pc_http', { status: res.status }));
      }
      var data;
      try {
        data = JSON.parse(res.text);
      } catch (e) {
        throw discError('not_json', t('err_not_json'));
      }
      if (!data || typeof data !== 'object') throw discError('bad_shape', t('err_pc_shape'));
      return data;
    });
}

function parsePing(data) {
  if (!data || data.ok !== true || data.app !== 'Krouchi_DZ') {
    throw discError('notapp', t('err_pc_notapp'));
  }
  return { ok: true, app: data.app, version: String(data.version || '') };
}

function parsePcBots(data) {
  var items = (data && typeof data === 'object') ? data.bots : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_pc_shape'));
  var bots = [];
  items.forEach(function (b) {
    if (b && typeof b === 'object' && b.id != null && b.name != null) {
      bots.push({
        id: String(b.id), name: String(b.name),
        provider: String(b.provider || ''), model: String(b.model || ''),
        mode: String(b.mode || '')
      });
    }
  });
  return bots;
}

function parsePcHistory(data) {
  var items = (data && typeof data === 'object') ? data.messages : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_pc_shape'));
  var messages = [];
  items.forEach(function (m) {
    if (m && typeof m === 'object' && typeof m.content === 'string') {
      messages.push({
        role: typeof m.role === 'string' ? m.role : 'assistant',
        content: m.content
      });
    }
  });
  return messages;
}

function parsePcApprovals(data) {
  var items = (data && typeof data === 'object') ? data.pending : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_pc_shape'));
  var pending = [];
  items.forEach(function (a) {
    if (a && typeof a === 'object' && a.id != null) {
      pending.push({
        id: String(a.id),
        bot_name: String(a.bot_name || ''), tool: String(a.tool || ''),
        summary: String(a.summary || ''), created: String(a.created || '')
      });
    }
  });
  return pending;
}

function parsePcChatReply(data) {
  if (!data || typeof data.reply !== 'string') {
    throw discError('bad_shape', t('err_pc_shape'));
  }
  return data.reply;
}

/* مُستطلِع دوري قابل للحقن بمؤقّتات وهمية في الاختبارات:
 * يبدأ فوراً، ويمنع تزامن جولتين، ويتوقف نظيفاً. */
function createPoller(options) {
  options = options || {};
  var intervalMs = options.intervalMs || 4000;
  var task = options.task;
  var onResult = options.onResult || function () {};
  var onError = options.onError || function () {};
  var setInt = options.setIntervalFn ||
    (typeof setInterval !== 'undefined' ? setInterval : null);
  var clearInt = options.clearIntervalFn ||
    (typeof clearInterval !== 'undefined' ? clearInterval : null);
  var timer = null;
  var running = false;
  var inFlight = false;

  function tick() {
    if (!running || inFlight || !task) return;
    inFlight = true;
    var done = function () { inFlight = false; };
    try {
      Promise.resolve(task()).then(
        function (r) { done(); onResult(r); },
        function (e) { done(); onError(e); });
    } catch (e) {
      done();
      onError(e);
    }
  }

  return {
    start: function () {
      if (running) return;
      running = true;
      tick();
      if (setInt) timer = setInt(tick, intervalMs);
    },
    stop: function () {
      running = false;
      if (timer != null && clearInt) clearInt(timer);
      timer = null;
    },
    tick: tick,
    isRunning: function () { return running; }
  };
}

/* تصدير للاختبارات (Node) — لا أثر له داخل الويب فيو */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    STRINGS: STRINGS, SUPPORTED_LANGS: SUPPORTED_LANGS, LS_LANG: LS_LANG,
    t: t, translate: translate, getLang: getLang, setLang: setLang,
    loadLang: loadLang, saveLang: saveLang, localizeDocument: localizeDocument,
    ERR_BAD_URL: ERR_BAD_URL, ERR_UNREACHABLE: ERR_UNREACHABLE, ERR_AUTH: ERR_AUTH,
    ERR_NOT_JSON: ERR_NOT_JSON, ERR_BAD_SHAPE: ERR_BAD_SHAPE, ERR_EMPTY: ERR_EMPTY,
    ERR_NO_KEY: ERR_NO_KEY, ERR_CHAT_SHAPE: ERR_CHAT_SHAPE,
    ERR_PC_UNREACHABLE: ERR_PC_UNREACHABLE, ERR_PC_TOKEN: ERR_PC_TOKEN,
    ERR_PC_NOTAPP: ERR_PC_NOTAPP, ERR_PC_SHAPE: ERR_PC_SHAPE,
    PC_DEFAULT_PORT: PC_DEFAULT_PORT, PC_CHAT_TIMEOUT_MS: PC_CHAT_TIMEOUT_MS,
    normalizeBaseUrl: normalizeBaseUrl, deriveName: deriveName,
    sanitizeName: sanitizeName, parseModelsOpenAI: parseModelsOpenAI,
    httpErrorFor: httpErrorFor, buildChatBody: buildChatBody,
    parseChatReply: parseChatReply,
    httpRequest: httpRequest, fetchTransport: fetchTransport,
    discoverModels: discoverModels, sendChat: sendChat,
    defaultPcConfig: defaultPcConfig, normalizePcConfig: normalizePcConfig,
    loadPcConfig: loadPcConfig, savePcConfig: savePcConfig,
    pcBaseUrl: pcBaseUrl, pcHeaders: pcHeaders, buildPcRequest: buildPcRequest,
    pcChatBody: pcChatBody, pcDecisionBody: pcDecisionBody, pcRequest: pcRequest,
    parsePing: parsePing, parsePcBots: parsePcBots,
    parsePcHistory: parsePcHistory, parsePcApprovals: parsePcApprovals,
    parsePcChatReply: parsePcChatReply, createPoller: createPoller
  };
}

/* ================= واجهة المستخدم (تعمل داخل الويب فيو فقط) ================= */
if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', initApp);
}

function el(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function toast(msg) {
  if (window.KrouchiBridge && window.KrouchiBridge.toast) {
    window.KrouchiBridge.toast(msg);
  }
}

var currentChatBotId = null;

/* إعادة رسم كل النصوص المرئية باللغة الحالية: النصوص الثابتة عبر
 * localizeDocument، والقوائم الديناميكية عبر دوال العرض نفسها. */
function applyLang() {
  if (typeof document === 'undefined') return;
  localizeDocument(document, LANG);
  ['lang-select', 'lang-select-about'].forEach(function (id) {
    var sel = el(id);
    if (sel) sel.value = LANG;
  });
  renderProviders();
  renderBots();
  refreshBotForms();
  renderChat();
  if (pcConnected) {
    renderPcBots(lastPcBots);
    renderPcApprovals(lastPcApprovals);
    if (currentPcBot) {
      el('pc-chat-title').textContent = t('pc_chat_with', { name: currentPcBot.name });
      renderPcChat();
    }
  }
}

function initApp() {
  var tabs = document.querySelectorAll('.tabbtn');
  tabs.forEach(function (btn) {
    btn.addEventListener('click', function () { showTab(btn.getAttribute('data-tab')); });
  });
  el('api-fetch').addEventListener('click', onApiFetch);
  el('bot-create').addEventListener('click', onBotCreate);
  el('bot-provider').addEventListener('change', refreshModelDatalist);
  el('chat-send').addEventListener('click', onChatSend);
  el('chat-clear').addEventListener('click', onChatClear);
  el('chat-bot').addEventListener('change', function () {
    currentChatBotId = el('chat-bot').value || null;
    renderChat();
  });
  el('pc-connect').addEventListener('click', onPcConnect);
  el('pc-chat-send').addEventListener('click', onPcChatSend);
  el('pc-chat-back').addEventListener('click', closePcChat);
  ['lang-select', 'lang-select-about'].forEach(function (id) {
    var sel = el(id);
    if (sel) sel.addEventListener('change', function () { setLang(sel.value); });
  });
  fillPcForm(loadPcConfig());
  applyLang();
}

function showTab(name) {
  ['api', 'bots', 'chat', 'pc', 'about'].forEach(function (tb) {
    el('tab-' + tb).style.display = (tb === name) ? 'block' : 'none';
  });
  document.querySelectorAll('.tabbtn').forEach(function (btn) {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === name);
  });
  if (name === 'chat') renderChat();
  /* استطلاع الموافقات يعمل فقط أثناء ظهور تبويب الحاسوب */
  if (name === 'pc') {
    if (pcConnected) {
      refreshPcBots();
      startPcApprovalsPolling();
    }
  } else {
    stopPcApprovalsPolling();
  }
}

/* ---------- تبويب إدخال API ---------- */
function setApiStatus(msg, ok) {
  var box = el('api-status');
  box.textContent = msg;
  box.className = 'status ' + (ok === true ? 'ok' : ok === false ? 'err' : '');
}

function onApiFetch() {
  var rawUrl = el('api-url').value;
  var key = el('api-key').value.trim();
  var name = el('api-name').value;
  var base;
  try {
    base = normalizeBaseUrl(rawUrl);
  } catch (e) {
    setApiStatus(e.message, false);
    return;
  }
  if (!key) {
    setApiStatus(t('err_no_key'), false);
    return;
  }
  var btn = el('api-fetch');
  btn.disabled = true;
  setApiStatus(t('api_connecting'), null);
  el('api-models').innerHTML = '';
  discoverModels(base, key).then(function (models) {
    btn.disabled = false;
    var pname = name && name.trim() ? sanitizeName(name) : deriveName(base);
    upsertProvider({
      name: pname, base: base, key: key, models: models,
      verified: true, fetchedAt: Date.now()
    });
    setApiStatus(t('api_success', { name: pname, count: models.length }), true);
    el('api-models').innerHTML = models.map(function (m) {
      return '<li>' + escapeHtml(m) + '</li>';
    }).join('');
    renderProviders();
    refreshBotForms();
  }).catch(function (err) {
    btn.disabled = false;
    /* كنسخة سطح المكتب: يبقى المزوّد محفوظاً لكن مُعلَّماً غير مُتحقَّق */
    var pname = name && name.trim() ? sanitizeName(name) : deriveName(base);
    upsertProvider({
      name: pname, base: base, key: key, models: [],
      verified: false, fetchedAt: 0
    });
    setApiStatus(err.message || String(err), false);
    renderProviders();
    refreshBotForms();
  });
}

function renderProviders() {
  var list = loadProviders();
  var box = el('providers-list');
  if (!list.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('providers_none')) + '</p>';
    return;
  }
  box.innerHTML = list.map(function (p) {
    var badge = p.verified
      ? '<span class="badge ok">' + escapeHtml(t('badge_verified')) + '</span>'
      : '<span class="badge err">' + escapeHtml(t('badge_unverified')) + '</span>';
    return '<div class="card"><div class="card-title">' + escapeHtml(p.name) + ' ' + badge + '</div>'
      + '<div class="muted">' + escapeHtml(p.base) + '</div>'
      + '<div class="muted">' + escapeHtml(t('models_count', { count: p.models ? p.models.length : 0 })) + '</div>'
      + '<button class="danger" data-del-provider="' + p.id + '">'
      + escapeHtml(t('btn_delete_provider')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-del-provider]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-del-provider');
      saveProviders(loadProviders().filter(function (p) { return p.id !== id; }));
      renderProviders();
      refreshBotForms();
      toast(t('toast_provider_deleted'));
    });
  });
}

/* ---------- تبويب البوتات ---------- */
function refreshBotForms() {
  var providers = loadProviders();
  var sel = el('bot-provider');
  var current = sel.value;
  sel.innerHTML = providers.map(function (p) {
    return '<option value="' + p.id + '">' + escapeHtml(p.name)
      + (p.verified ? '' : escapeHtml(t('provider_unverified_suffix'))) + '</option>';
  }).join('');
  if (current && findProvider(current)) sel.value = current;
  refreshModelDatalist();

  var chatSel = el('chat-bot');
  var bots = loadBots();
  var curChat = chatSel.value;
  chatSel.innerHTML = bots.map(function (b) {
    return '<option value="' + b.id + '">' + escapeHtml(b.name) + '</option>';
  }).join('');
  if (curChat && bots.some(function (b) { return b.id === curChat; })) {
    chatSel.value = curChat;
  }
  currentChatBotId = chatSel.value || null;
}

function refreshModelDatalist() {
  var p = findProvider(el('bot-provider').value);
  var dl = el('bot-models');
  dl.innerHTML = (p && p.models ? p.models : []).map(function (m) {
    return '<option value="' + escapeHtml(m) + '"></option>';
  }).join('');
}

function onBotCreate() {
  var name = el('bot-name').value.trim();
  var provider = findProvider(el('bot-provider').value);
  var model = el('bot-model').value.trim();
  var system = el('bot-system').value;
  var status = el('bot-status');
  if (!name) { status.textContent = t('bot_err_name'); status.className = 'status err'; return; }
  if (!provider) { status.textContent = t('bot_err_provider'); status.className = 'status err'; return; }
  if (!model) { status.textContent = t('bot_err_model'); status.className = 'status err'; return; }
  var bots = loadBots();
  var bot = {
    id: 'b' + Date.now() + '_' + Math.floor(Math.random() * 1e6),
    name: name, providerId: provider.id, model: model, system: system
  };
  bots.push(bot);
  saveBots(bots);
  status.textContent = t('bot_created', { name: name });
  status.className = 'status ok';
  el('bot-name').value = '';
  renderBots();
  refreshBotForms();
}

function renderBots() {
  var bots = loadBots();
  var box = el('bots-list');
  if (!bots.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('bots_none')) + '</p>';
    return;
  }
  box.innerHTML = bots.map(function (b) {
    var p = findProvider(b.providerId);
    return '<div class="card"><div class="card-title">' + escapeHtml(b.name) + '</div>'
      + '<div class="muted">' + escapeHtml(p ? p.name : t('unknown_mark')) + ' — ' + escapeHtml(b.model) + '</div>'
      + '<button data-chat-bot="' + b.id + '">' + escapeHtml(t('btn_chat_with')) + '</button> '
      + '<button class="danger" data-del-bot="' + b.id + '">' + escapeHtml(t('btn_delete')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-chat-bot]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      currentChatBotId = btn.getAttribute('data-chat-bot');
      el('chat-bot').value = currentChatBotId;
      showTab('chat');
    });
  });
  box.querySelectorAll('[data-del-bot]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-del-bot');
      saveBots(loadBots().filter(function (b) { return b.id !== id; }));
      var chats = loadChats();
      delete chats[id];
      saveChats(chats);
      renderBots();
      refreshBotForms();
      renderChat();
      toast(t('toast_bot_deleted'));
    });
  });
}

/* ---------- تبويب المحادثة ---------- */
function currentBot() {
  var bots = loadBots();
  for (var i = 0; i < bots.length; i++) {
    if (bots[i].id === currentChatBotId) return bots[i];
  }
  return bots.length ? bots[0] : null;
}

function renderChat(transientError) {
  var bot = currentBot();
  var area = el('chat-messages');
  el('chat-send').disabled = !bot;
  if (!bot) {
    area.innerHTML = '<p class="muted">' + escapeHtml(t('chat_no_bot')) + '</p>';
    return;
  }
  var history = (loadChats()[bot.id]) || [];
  var html = history.map(function (m) {
    var cls = m.role === 'user' ? 'msg user' : 'msg bot';
    var who = m.role === 'user' ? t('you') : bot.name;
    return '<div class="' + cls + '"><div class="who">' + escapeHtml(who) + '</div>'
      + '<div class="text">' + escapeHtml(m.content) + '</div></div>';
  }).join('');
  if (transientError) {
    html += '<div class="msg error"><div class="text">' + escapeHtml(transientError) + '</div></div>';
  }
  area.innerHTML = html || '<p class="muted">' + escapeHtml(t('chat_empty')) + '</p>';
  area.scrollTop = area.scrollHeight;
}

function onChatSend() {
  var bot = currentBot();
  if (!bot) return;
  var provider = findProvider(bot.providerId);
  if (!provider) {
    renderChat(t('chat_provider_gone'));
    return;
  }
  var input = el('chat-input');
  var text = input.value.trim();
  if (!text) return;
  input.value = '';

  var chats = loadChats();
  var history = chats[bot.id] || [];
  history.push({ role: 'user', content: text });
  chats[bot.id] = history;
  saveChats(chats);
  renderChat();

  var convo = [];
  if (bot.system && bot.system.trim()) {
    convo.push({ role: 'system', content: bot.system });
  }
  convo = convo.concat(history);

  var btn = el('chat-send');
  btn.disabled = true;
  btn.textContent = t('chat_writing');
  sendChat(provider.base, provider.key, bot.model, convo).then(function (reply) {
    btn.disabled = false;
    btn.textContent = t('btn_send');
    var chats2 = loadChats();
    var h2 = chats2[bot.id] || [];
    h2.push({ role: 'assistant', content: reply });
    chats2[bot.id] = h2;
    saveChats(chats2);
    renderChat();
  }).catch(function (err) {
    btn.disabled = false;
    btn.textContent = t('btn_send');
    renderChat(err.message || String(err));
  });
}

function onChatClear() {
  var bot = currentBot();
  if (!bot) return;
  var chats = loadChats();
  chats[bot.id] = [];
  saveChats(chats);
  renderChat();
  toast(t('toast_chat_cleared', { name: bot.name }));
}

/* ---------- تبويب الحاسوب (الوضع المرافق) ---------- */
var pcConnected = false;
var pcCfg = null;
var currentPcBot = null;
var lastPcMessages = [];
var lastPcBots = [];
var lastPcApprovals = [];
var pcApprovalsPoller = null;

function pcModeLabel(mode) {
  var key = 'mode_' + mode;
  var label = t(key);
  return label === key ? mode : label;
}

function fillPcForm(cfg) {
  el('pc-host').value = cfg.host || '';
  el('pc-port').value = cfg.port || PC_DEFAULT_PORT;
  el('pc-token').value = cfg.token || '';
}

function readPcForm() {
  return normalizePcConfig({
    host: el('pc-host').value,
    port: el('pc-port').value,
    token: el('pc-token').value
  });
}

function setPcStatus(msg, ok) {
  var box = el('pc-status');
  box.textContent = msg;
  box.className = 'status ' + (ok === true ? 'ok' : ok === false ? 'err' : '');
}

function onPcConnect() {
  var cfg = readPcForm();
  try {
    pcBaseUrl(cfg);
  } catch (e) {
    setPcStatus(t('pc_err_host'), false);
    return;
  }
  if (!cfg.token) {
    setPcStatus(t('pc_err_token'), false);
    return;
  }
  /* تُحفظ الإعدادات في تخزين التطبيق حتى تبقى للمرة القادمة */
  pcCfg = savePcConfig(cfg);
  var btn = el('pc-connect');
  btn.disabled = true;
  btn.textContent = t('pc_connecting_btn');
  setPcStatus(t('pc_testing'), null);
  pcRequest(pcCfg, 'GET', '/api/ping').then(function (data) {
    var info = parsePing(data);
    btn.disabled = false;
    btn.textContent = t('btn_connect');
    pcConnected = true;
    el('pc-connected').style.display = 'block';
    setPcStatus(t('pc_connected')
      + (info.version ? t('pc_connected_version', { version: info.version }) : ''), true);
    refreshPcBots();
    startPcApprovalsPolling();
  }).catch(function (err) {
    btn.disabled = false;
    btn.textContent = t('btn_connect');
    pcConnected = false;
    el('pc-connected').style.display = 'none';
    stopPcApprovalsPolling();
    setPcStatus(err.message || String(err), false);
  });
}

function refreshPcBots() {
  if (!pcConnected || !pcCfg) return;
  pcRequest(pcCfg, 'GET', '/api/bots').then(function (data) {
    renderPcBots(parsePcBots(data));
  }).catch(function (err) {
    el('pc-bots-list').innerHTML =
      '<p class="muted">' + escapeHtml(err.message || String(err)) + '</p>';
  });
}

function renderPcBots(bots) {
  lastPcBots = bots || [];
  var box = el('pc-bots-list');
  if (!lastPcBots.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('pc_bots_none')) + '</p>';
    return;
  }
  box.innerHTML = lastPcBots.map(function (b) {
    var mode = b.mode ? pcModeLabel(b.mode) : '';
    return '<div class="card"><div class="card-title">🖥️ ' + escapeHtml(b.name) + '</div>'
      + '<div class="muted">' + escapeHtml(b.provider) + ' — ' + escapeHtml(b.model) + '</div>'
      + (mode ? '<div class="muted">' + escapeHtml(t('pc_mode_line', { mode: mode })) + '</div>' : '')
      + '<button data-pc-chat="' + escapeHtml(b.id) + '" data-pc-name="'
      + escapeHtml(b.name) + '">' + escapeHtml(t('btn_pc_chat')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-pc-chat]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      openPcChat(btn.getAttribute('data-pc-chat'), btn.getAttribute('data-pc-name'));
    });
  });
}

/* ---------- محادثة الحاسوب ---------- */
function openPcChat(botId, botName) {
  var idNum = Number(botId);
  if (!isNaN(idNum)) botId = idNum;
  currentPcBot = { id: botId, name: botName || t('pc_bot_fallback_name') };
  el('pc-bots-wrap').style.display = 'none';
  el('pc-chat-wrap').style.display = 'block';
  el('pc-chat-title').textContent = t('pc_chat_with', { name: currentPcBot.name });
  loadPcHistory();
}

function closePcChat() {
  currentPcBot = null;
  lastPcMessages = [];
  el('pc-chat-wrap').style.display = 'none';
  el('pc-bots-wrap').style.display = 'block';
  refreshPcBots();
}

function loadPcHistory() {
  if (!currentPcBot || !pcCfg) return;
  var botId = currentPcBot.id;
  pcRequest(pcCfg, 'GET', '/api/history?bot=' + encodeURIComponent(botId))
    .then(function (data) {
      if (!currentPcBot || currentPcBot.id !== botId) return;
      lastPcMessages = parsePcHistory(data);
      renderPcChat();
    }).catch(function (err) {
      renderPcChat(err.message || String(err));
    });
}

function renderPcChat(transientError) {
  var area = el('pc-chat-messages');
  var bot = currentPcBot;
  el('pc-chat-send').disabled = !bot;
  if (!bot) {
    area.innerHTML = '<p class="muted">' + escapeHtml(t('pc_chat_pick')) + '</p>';
    return;
  }
  var html = lastPcMessages.filter(function (m) {
    return m.role !== 'system';
  }).map(function (m) {
    var cls = m.role === 'user' ? 'msg user' : 'msg bot';
    var who = m.role === 'user' ? t('you') : bot.name;
    return '<div class="' + cls + '"><div class="who">' + escapeHtml(who) + '</div>'
      + '<div class="text">' + escapeHtml(m.content) + '</div></div>';
  }).join('');
  if (transientError) {
    html += '<div class="msg error"><div class="text">' + escapeHtml(transientError) + '</div></div>';
  }
  area.innerHTML = html || '<p class="muted">' + escapeHtml(t('chat_empty')) + '</p>';
  area.scrollTop = area.scrollHeight;
}

function onPcChatSend() {
  if (!currentPcBot || !pcCfg) return;
  var input = el('pc-chat-input');
  var text = input.value.trim();
  if (!text) return;
  input.value = '';
  var bot = currentPcBot;
  /* عرض فوري لرسالة المستخدم، ثم إعادة تحميل السجل من الحاسوب */
  lastPcMessages = lastPcMessages.concat([{ role: 'user', content: text }]);
  renderPcChat();
  var btn = el('pc-chat-send');
  btn.disabled = true;
  btn.textContent = t('pc_chat_sending');
  pcRequest(pcCfg, 'POST', '/api/chat', pcChatBody(bot.id, text), PC_CHAT_TIMEOUT_MS)
    .then(function (data) {
      btn.disabled = false;
      btn.textContent = t('btn_send');
      parsePcChatReply(data);
      if (currentPcBot && currentPcBot.id === bot.id) loadPcHistory();
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = t('btn_send');
      renderPcChat(err.message || String(err));
    });
}

/* ---------- موافقات الحاسوب ---------- */
function startPcApprovalsPolling() {
  if (pcApprovalsPoller || !pcConnected || !pcCfg) return;
  pcApprovalsPoller = createPoller({
    intervalMs: 4000,
    task: function () {
      return pcRequest(pcCfg, 'GET', '/api/approvals')
        .then(function (data) { return parsePcApprovals(data); });
    },
    onResult: function (pending) { renderPcApprovals(pending); },
    onError: function () { /* خطأ عابر: تبقى القائمة كما هي ونعيد المحاولة */ }
  });
  pcApprovalsPoller.start();
}

function stopPcApprovalsPolling() {
  if (pcApprovalsPoller) {
    pcApprovalsPoller.stop();
    pcApprovalsPoller = null;
  }
}

function renderPcApprovals(pending) {
  lastPcApprovals = pending || [];
  var box = el('pc-approvals-list');
  var count = el('pc-approvals-count');
  if (lastPcApprovals.length) {
    count.style.display = '';
    count.textContent = t('approvals_waiting', { count: lastPcApprovals.length });
  } else {
    count.style.display = 'none';
  }
  if (!lastPcApprovals.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('approvals_none')) + '</p>';
    return;
  }
  box.innerHTML = lastPcApprovals.map(function (a) {
    return '<div class="card"><div class="card-title">'
      + escapeHtml(t('approval_request_from', { name: a.bot_name || t('approval_bot_fallback') })) + '</div>'
      + (a.tool ? '<div class="muted">' + escapeHtml(t('approval_tool', { tool: a.tool })) + '</div>' : '')
      + '<div>' + escapeHtml(a.summary) + '</div>'
      + (a.created ? '<div class="muted">' + escapeHtml(a.created) + '</div>' : '')
      + '<button class="approve" data-pc-approve="' + escapeHtml(a.id) + '">'
      + escapeHtml(t('btn_approve')) + '</button> '
      + '<button class="danger" data-pc-deny="' + escapeHtml(a.id) + '">'
      + escapeHtml(t('btn_deny')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-pc-approve]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      decidePcApproval(btn.getAttribute('data-pc-approve'), 'approve');
    });
  });
  box.querySelectorAll('[data-pc-deny]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      decidePcApproval(btn.getAttribute('data-pc-deny'), 'deny');
    });
  });
}

function decidePcApproval(id, decision) {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'POST', '/api/approvals/' + encodeURIComponent(id),
    pcDecisionBody(decision))
    .then(function () {
      toast(decision === 'approve' ? t('toast_approved') : t('toast_denied'));
      if (pcApprovalsPoller) pcApprovalsPoller.tick();
    }).catch(function (err) {
      toast(err.message || String(err));
    });
}
