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
    label_pc_mac: 'عنوان MAC لبطاقة شبكة الحاسوب',
    ph_pc_mac: 'AA:BB:CC:DD:EE:FF',
    btn_pc_wake: 'إيقاظ الحاسوب',
    pc_wake_sent: 'أُرسلت حزمة الإيقاظ إلى الحاسوب',
    pc_wake_unsupported: 'الإيقاظ يعمل من تطبيق الأندرويد فقط، حين يكون الهاتف على شبكة البيت',
    pc_wake_bad_mac: 'عنوان MAC غير صالح — الصيغة: AA:BB:CC:DD:EE:FF',
    pc_pending_approvals: 'الموافقات المعلّقة',
    pc_approvals_note: 'حين يطلب بوت على الحاسوب تنفيذ إجراء، يظهر طلبه هنا لتُوافق عليه أو ترفضه — وعدم الجواب يبقيه معلّقاً على الحاسوب.',
    pc_bots_title: 'بوتات الحاسوب',
    pc_chat_title: 'محادثة الحاسوب',
    btn_pc_back: 'عودة إلى بوتات الحاسوب',
    about_title: 'حول Krouchi_DZ',
    about_author: 'تأليف: كروشي عبد الرزاق',
    about_p1: 'الإصدار 3.3.1 — رفيق الهاتف لبرنامج Krouchi_DZ المكتبي، بشيفرة أصلية مكتوبة من الصفر.',
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
    toast_denied: 'أُرسل الرفض إلى الحاسوب',
    pc_tasks_title: 'المهام',
    label_task_bot: 'البوت المنفِّذ',
    label_task_title: 'عنوان المهمة',
    ph_task_title: 'مثال: لخّص ملفّ الملاحظات',
    label_task_prompt: 'نصّ المهمة',
    ph_task_prompt: 'اكتب ما تريد من البوت أن يفعله على الحاسوب…',
    btn_task_create: 'إرسال المهمة إلى الحاسوب',
    task_err_bot: 'اختر بوتاً من بوتات الحاسوب أولاً',
    task_err_title: 'أدخل عنواناً للمهمة',
    task_err_prompt: 'اكتب نصّ المهمة',
    task_created: 'أُرسلت المهمة «{title}» إلى الحاسوب',
    tasks_none: 'لا مهام بعد — أرسل أول مهمة من النموذج أعلاه.',
    task_status_queued: 'في الانتظار',
    task_status_running: 'قيد التنفيذ',
    task_status_waiting_approval: 'بانتظار الموافقة',
    task_status_done: 'تمّت',
    task_status_failed: 'فشلت',
    task_status_cancelled: 'أُلغيت',
    task_status_unknown: 'حالة غير معروفة',
    task_bot_line: 'البوت: {name}',
    task_detail_prompt: 'نصّ المهمة',
    task_detail_result: 'النتيجة',
    task_detail_error: 'الخطأ',
    task_detail_log: 'سجلّ التنفيذ',
    task_log_empty: 'لا سجلّ بعد.',
    btn_task_cancel: 'إلغاء المهمة',
    btn_back_tasks: 'عودة إلى المهام',
    btn_details: 'التفاصيل',
    toast_task_cancelled: 'أُرسل طلب الإلغاء إلى الحاسوب',
    pc_control_title: 'التحكّم بالحاسوب',
    btn_refresh: 'تحديث',
    status_hostname: 'اسم الحاسوب',
    status_os: 'النظام',
    status_platform: 'المنصّة',
    status_version: 'إصدار Krouchi_DZ',
    status_uptime: 'مدّة التشغيل',
    status_disk: 'القرص',
    status_disk_value: '{free} GB حرّ من أصل {total} GB',
    status_ram: 'الذاكرة (RAM)',
    status_ram_value: '{mb} MB',
    size_bytes: '{n} بايت',
    size_kb: '{n} KB',
    size_mb: '{n} MB',
    files_title: 'ملفّات الحاسوب',
    btn_up: '⬆️ المجلد الأعلى',
    files_empty: 'هذا المجلد فارغ.',
    btn_open_folder: 'فتح',
    btn_download: 'تنزيل',
    toast_download_started: 'بدأ تنزيل «{name}»',
    run_title: 'تشغيل أمر',
    label_run_command: 'الأمر',
    ph_run_command: 'الأمر المراد تشغيله على الحاسوب',
    btn_run: 'تشغيل',
    run_note: 'قد يطلب الحاسوب موافقتك قبل التنفيذ — يظهر الطلب في قسم «الموافقات المعلّقة» أعلاه أو على شاشة الحاسوب نفسه.',
    run_running: 'جارٍ التنفيذ على الحاسوب…',
    run_exit: 'رمز الخروج: {code}',
    run_timed_out: 'انقضت مهلة التنفيذ',
    err_denied: 'رفض الحاسوب التنفيذ — لم تتمّ الموافقة على الطلب',
    open_title: 'فتح برنامج أو ملف أو رابط',
    label_open_target: 'الهدف (اسم برنامج أو مسار أو رابط)',
    ph_open_target: 'notepad أو https://…',
    btn_open: 'فتح على الحاسوب',
    toast_opened: 'أُرسل طلب الفتح إلى الحاسوب',
    screenshot_title: 'لقطة شاشة الحاسوب',
    btn_screenshot: 'التقط لقطة',
    power_title: 'الطاقة',
    btn_shutdown: 'إيقاف الحاسوب',
    btn_restart: 'إعادة التشغيل',
    btn_lock: 'قفل',
    btn_sleep: 'نوم',
    btn_logoff: 'تسجيل الخروج',
    btn_confirm_action: 'متأكّد؟ اضغط مجدّداً للتأكيد',
    power_scheduled: 'سيُنفَّذ الإجراء خلال {seconds} ثانية',
    power_done: 'نُفِّذ الإجراء على الحاسوب',
    printers_title: 'الطابعات',
    label_printer: 'الطابعة',
    printer_auto: 'الافتراضية على الحاسوب',
    printer_default_suffix: ' (الافتراضية)',
    printers_none: 'لا طابعات معرّفة على الحاسوب.',
    btn_print: '🖨️ طباعة',
    toast_print_sent: 'أُرسل «{name}» إلى الطباعة',
    upload_title: 'رفع ملف إلى الحاسوب',
    upload_note: 'يُحفظ الملف المرفوع في المجلد المعروض حالياً في متصفّح الملفّات أعلاه.',
    upload_sending: 'جارٍ رفع «{name}»…',
    upload_done: 'رُفع «{name}» إلى الحاسوب ({size})',
    clipboard_title: 'حافظة الحاسوب',
    ph_clipboard: 'نصّ الحافظة…',
    btn_clip_get: 'جلب نصّ حافظة الحاسوب',
    btn_clip_set: 'إرسال إلى حافظة الحاسوب',
    clip_empty: 'حافظة الحاسوب فارغة.',
    toast_clip_sent: 'أُرسل النصّ إلى حافظة الحاسوب',
    volume_title: 'الصوت',
    btn_vol_down: '🔉 خفض',
    btn_vol_mute: '🔇 كتم',
    btn_vol_up: '🔊 رفع',
    toast_volume: 'أُرسل أمر الصوت إلى الحاسوب',
    windows_title: 'النوافذ المفتوحة',
    windows_none: 'لا نوافذ مفتوحة.',
    btn_win_focus: 'تركيز',
    btn_win_minimize: 'تصغير',
    btn_win_maximize: 'تكبير',
    btn_win_close: 'إغلاق',
    toast_window_action: 'أُرسل إجراء النافذة إلى الحاسوب',
    processes_title: 'العمليات',
    processes_none: 'لا عمليات.',
    proc_line: 'PID {pid} — {mem}',
    btn_kill: 'إنهاء',
    toast_kill_sent: 'أُرسل طلب إنهاء العملية إلى الحاسوب',
    screen_title: 'شاشة الحاسوب الحية',
    screen_note: 'بثّ مباشر لشاشة الحاسوب — المس الصورة للنقر، واضغط مطوّلاً للنقر الأيمن، واسحب لتحريك المؤشّر.',
    btn_screen_start: 'بدء الشاشة',
    btn_screen_stop: 'إيقاف',
    btn_screen_drag: 'سحب النوافذ',
    screen_err: 'تعذّر بدء بثّ الشاشة — تحقّق من الاتصال، ومن تفعيل التحكّم على الحاسوب ودعمه للبثّ.',
    screen_input_failed: 'تعذّر إرسال الإدخال إلى الحاسوب',
    label_screen_text: 'نصّ يُكتب على الحاسوب',
    ph_screen_text: 'اكتب نصّاً ليُكتَب على الحاسوب…',
    btn_screen_send_text: 'إرسال النص',
    screen_keys_title: 'مفاتيح خاصة',
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
    label_pc_mac: 'PC network card MAC address',
    ph_pc_mac: 'AA:BB:CC:DD:EE:FF',
    btn_pc_wake: 'Wake the computer',
    pc_wake_sent: 'Wake packet sent to the computer',
    pc_wake_unsupported: 'Wake works from the Android app only, while the phone is on the home network',
    pc_wake_bad_mac: 'Invalid MAC address — format: AA:BB:CC:DD:EE:FF',
    pc_pending_approvals: 'Pending approvals',
    pc_approvals_note: 'When a bot on the computer asks to execute an action, its request appears here for you to approve or deny — no answer leaves it pending on the computer.',
    pc_bots_title: 'Computer bots',
    pc_chat_title: 'Computer chat',
    btn_pc_back: 'Back to computer bots',
    about_title: 'About Krouchi_DZ',
    about_author: 'By Krouchi Abderrazak',
    about_p1: 'Version 3.3.1 — the phone companion to the Krouchi_DZ desktop program, with original code written from scratch.',
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
    toast_denied: 'Denial sent to the computer',
    pc_tasks_title: 'Tasks',
    label_task_bot: 'Executing bot',
    label_task_title: 'Task title',
    ph_task_title: 'e.g. Summarize the notes file',
    label_task_prompt: 'Task prompt',
    ph_task_prompt: 'Write what you want the bot to do on the computer…',
    btn_task_create: 'Send task to the computer',
    task_err_bot: 'Pick one of the computer bots first',
    task_err_title: 'Enter a title for the task',
    task_err_prompt: 'Write the task prompt',
    task_created: 'Task "{title}" sent to the computer',
    tasks_none: 'No tasks yet — send your first task from the form above.',
    task_status_queued: 'Queued',
    task_status_running: 'Running',
    task_status_waiting_approval: 'Waiting for approval',
    task_status_done: 'Done',
    task_status_failed: 'Failed',
    task_status_cancelled: 'Cancelled',
    task_status_unknown: 'Unknown status',
    task_bot_line: 'Bot: {name}',
    task_detail_prompt: 'Prompt',
    task_detail_result: 'Result',
    task_detail_error: 'Error',
    task_detail_log: 'Execution log',
    task_log_empty: 'No log entries yet.',
    btn_task_cancel: 'Cancel task',
    btn_back_tasks: 'Back to tasks',
    btn_details: 'Details',
    toast_task_cancelled: 'Cancellation request sent to the computer',
    pc_control_title: 'Computer control',
    btn_refresh: 'Refresh',
    status_hostname: 'Computer name',
    status_os: 'System',
    status_platform: 'Platform',
    status_version: 'Krouchi_DZ version',
    status_uptime: 'Uptime',
    status_disk: 'Disk',
    status_disk_value: '{free} GB free of {total} GB',
    status_ram: 'Memory (RAM)',
    status_ram_value: '{mb} MB',
    size_bytes: '{n} B',
    size_kb: '{n} KB',
    size_mb: '{n} MB',
    files_title: 'Computer files',
    btn_up: '⬆️ Parent folder',
    files_empty: 'This folder is empty.',
    btn_open_folder: 'Open',
    btn_download: 'Download',
    toast_download_started: 'Download of "{name}" started',
    run_title: 'Run a command',
    label_run_command: 'Command',
    ph_run_command: 'Command to run on the computer',
    btn_run: 'Run',
    run_note: 'The computer may ask for your approval before running — the request appears in the "Pending approvals" section above or on the computer screen itself.',
    run_running: 'Running on the computer…',
    run_exit: 'Exit code: {code}',
    run_timed_out: 'Execution timed out',
    err_denied: 'The computer denied the action — the request was not approved',
    open_title: 'Open a program, file or link',
    label_open_target: 'Target (program name, path or URL)',
    ph_open_target: 'notepad or https://…',
    btn_open: 'Open on the computer',
    toast_opened: 'Open request sent to the computer',
    screenshot_title: 'Computer screenshot',
    btn_screenshot: 'Take a screenshot',
    power_title: 'Power',
    btn_shutdown: 'Shut down',
    btn_restart: 'Restart',
    btn_lock: 'Lock',
    btn_sleep: 'Sleep',
    btn_logoff: 'Log off',
    btn_confirm_action: 'Are you sure? Tap again to confirm',
    power_scheduled: 'The action will run in {seconds} seconds',
    power_done: 'The action was carried out on the computer',
    printers_title: 'Printers',
    label_printer: 'Printer',
    printer_auto: 'The computer\'s default',
    printer_default_suffix: ' (default)',
    printers_none: 'No printers defined on the computer.',
    btn_print: '🖨️ Print',
    toast_print_sent: '"{name}" sent to print',
    upload_title: 'Upload a file to the computer',
    upload_note: 'The uploaded file is saved in the folder currently shown in the file browser above.',
    upload_sending: 'Uploading "{name}"…',
    upload_done: '"{name}" uploaded to the computer ({size})',
    clipboard_title: 'Computer clipboard',
    ph_clipboard: 'Clipboard text…',
    btn_clip_get: 'Fetch the computer\'s clipboard',
    btn_clip_set: 'Send to the computer\'s clipboard',
    clip_empty: 'The computer\'s clipboard is empty.',
    toast_clip_sent: 'Text sent to the computer clipboard',
    volume_title: 'Volume',
    btn_vol_down: '🔉 Down',
    btn_vol_mute: '🔇 Mute',
    btn_vol_up: '🔊 Up',
    toast_volume: 'Volume command sent to the computer',
    windows_title: 'Open windows',
    windows_none: 'No open windows.',
    btn_win_focus: 'Focus',
    btn_win_minimize: 'Minimize',
    btn_win_maximize: 'Maximize',
    btn_win_close: 'Close',
    toast_window_action: 'Window action sent to the computer',
    processes_title: 'Processes',
    processes_none: 'No processes.',
    proc_line: 'PID {pid} — {mem}',
    btn_kill: 'End task',
    toast_kill_sent: 'Kill request sent to the computer',
    screen_title: 'Live computer screen',
    screen_note: 'A live stream of the computer screen — tap the picture to click, long-press for a right click, drag to move the pointer.',
    btn_screen_start: 'Start screen',
    btn_screen_stop: 'Stop',
    btn_screen_drag: 'Drag windows',
    screen_err: 'Could not start the screen stream — check the connection, and that control is enabled and streaming is supported on the computer.',
    screen_input_failed: 'Could not send the input to the computer',
    label_screen_text: 'Text to type on the computer',
    ph_screen_text: 'Type text to be typed on the computer…',
    btn_screen_send_text: 'Send text',
    screen_keys_title: 'Special keys',
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
/* مهلة تشغيل أمر على الحاسوب: قد ينتظر موافقة قبل التنفيذ */
var PC_RUN_TIMEOUT_MS = 180000;

var ERR_PC_UNREACHABLE = STRINGS.ar.err_pc_unreachable;
var ERR_PC_TOKEN = STRINGS.ar.err_pc_token;
var ERR_PC_NOTAPP = STRINGS.ar.err_pc_notapp;
var ERR_PC_SHAPE = STRINGS.ar.err_pc_shape;
var ERR_PC_DENIED = STRINGS.ar.err_denied;

/* تطبيع عنوان MAC: يقبل AA:BB:CC:DD:EE:FF أو AA-BB-CC-DD-EE-FF
 * أو 12 رقماً سداسياً متصلاً (بأي حالة أحرف)؛ يعيد الصيغة القانونية
 * بأحرف كبيرة مفصولة بنقطتين، أو null عند أي صيغة غير صالحة */
function normalizeMac(mac) {
  if (mac == null) return null;
  var hex = String(mac).trim().replace(/[:\-\s]/g, '');
  if (!/^[0-9A-Fa-f]{12}$/.test(hex)) return null;
  hex = hex.toUpperCase();
  var parts = [];
  for (var i = 0; i < 12; i += 2) parts.push(hex.substr(i, 2));
  return parts.join(':');
}

function defaultPcConfig() {
  return { host: '', port: PC_DEFAULT_PORT, token: '', mac: '' };
}

function normalizePcConfig(cfg) {
  cfg = cfg || {};
  var port = parseInt(cfg.port, 10);
  if (!port || port < 1 || port > 65535) port = PC_DEFAULT_PORT;
  return {
    host: String(cfg.host == null ? '' : cfg.host).trim(),
    port: port,
    token: String(cfg.token == null ? '' : cfg.token).trim(),
    mac: normalizeMac(cfg.mac) || ''
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
  return { bot_id: coerceNumericId(botId), text: text };
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
        var denied403 = false;
        if (res.status === 403 && res.text) {
          try {
            var parsed403 = JSON.parse(res.text);
            denied403 = !!(parsed403 && parsed403.error === 'denied');
          } catch (e) { denied403 = false; }
        }
        if (denied403) throw discError('denied', t('err_denied'));
        throw discError('auth', t('err_pc_token'));
      }
      if (res.status < 200 || res.status >= 300) {
        /* نصّ خطأ الخادم نفسه (حقل error في JSON) يُلحَق بالرسالة —
         * بدونه لا يرى المستخدم إلا رقم HTTP ولا يعرف السبب */
        var serverError = '';
        if (res.text) {
          try {
            var parsedErr = JSON.parse(res.text);
            if (parsedErr && typeof parsedErr.error === 'string') {
              serverError = parsedErr.error;
            }
          } catch (e) { serverError = ''; }
        }
        throw discError('http',
          t('err_pc_http', { status: res.status }) +
          (serverError ? ' — ' + serverError : ''));
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

/* ================= المهام والتحكّم الكلّي (v3.2): دوال نقية =================
 * عقد الخادم الإضافي (نفس pcRequest ورمز الاقتران):
 *   GET  /api/status                  → حالة الحاسوب
 *   GET  /api/files?path=             → قائمة مجلد
 *   GET  /api/file?path=              → ملف مشفّراً بـ Base64
 *   POST /api/run {command}           → {exit, stdout, stderr, timed_out}
 *   POST /api/open {target}           → {ok}
 *   GET  /api/screenshot              → {image_b64, format}
 *   POST /api/power {action}          → {ok, scheduled_in_s}
 *   GET  /api/printers                → {printers:[{name, is_default}]}
 *   POST /api/print {path, printer?}  → {ok}   (قد يُرفَض 403 denied)
 *   POST /api/upload {path, content_b64} → {ok, size}  (قد يُرفَض)
 *   GET  /api/clipboard               → {text}
 *   POST /api/clipboard {text}        → {ok}   (قد يُرفَض)
 *   POST /api/volume {action}         → {ok}
 *   GET  /api/windows                 → {windows:[{id, title}]}
 *   POST /api/window {id, action}     → {ok}   (قد يُرفَض)
 *   GET  /api/processes               → {processes:[{pid, name, mem_mb}]}
 *   POST /api/process/kill {pid}      → {ok}   (قد يُرفَض)
 *   POST /api/tasks {bot_id, title, prompt} → {task:{…}}
 *   GET  /api/tasks                   → {tasks:[…]}
 *   GET  /api/tasks/<id>              → {task:{…, log:[…]}}
 *   POST /api/tasks/<id>/cancel       → {ok}
 */

/* تحويل معرّف نصّي رقمي إلى رقم (يصل من خصائص HTML كنصّ دائماً) */
function coerceNumericId(id) {
  if (typeof id === 'string' && /^-?\d+$/.test(id.trim())) return Number(id);
  return id;
}

/* ---------- المهام ---------- */
var TASK_STATUSES = ['queued', 'running', 'waiting_approval', 'done', 'failed', 'cancelled'];

function taskBody(botId, title, prompt) {
  return {
    bot_id: coerceNumericId(botId),
    title: String(title == null ? '' : title),
    prompt: String(prompt == null ? '' : prompt)
  };
}

function normalizeTask(raw) {
  if (!raw || typeof raw !== 'object' || raw.id == null) return null;
  return {
    id: String(raw.id),
    bot_id: raw.bot_id == null ? '' : raw.bot_id,
    bot_name: String(raw.bot_name || ''),
    title: String(raw.title || ''),
    status: String(raw.status || ''),
    created_at: String(raw.created_at || ''),
    started_at: String(raw.started_at || ''),
    finished_at: String(raw.finished_at || '')
  };
}

function parseTasks(data) {
  var items = (data && typeof data === 'object') ? data.tasks : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_pc_shape'));
  var tasks = [];
  items.forEach(function (raw) {
    var task = normalizeTask(raw);
    if (task) tasks.push(task);
  });
  return tasks;
}

function parseTaskDetail(data) {
  var raw = (data && typeof data === 'object') ? data.task : null;
  var task = normalizeTask(raw);
  if (!task) throw discError('bad_shape', t('err_pc_shape'));
  task.prompt = String(raw.prompt || '');
  task.result = raw.result == null ? '' : String(raw.result);
  task.error = raw.error == null ? '' : String(raw.error);
  task.log = [];
  var logItems = Array.isArray(raw.log) ? raw.log : [];
  logItems.forEach(function (line) {
    if (line && typeof line === 'object') {
      task.log.push({
        ts: String(line.ts || ''), kind: String(line.kind || ''),
        text: String(line.text == null ? '' : line.text)
      });
    } else if (typeof line === 'string') {
      task.log.push({ ts: '', kind: '', text: line });
    }
  });
  return task;
}

function taskStatusKey(status) {
  return TASK_STATUSES.indexOf(status) >= 0
    ? 'task_status_' + status : 'task_status_unknown';
}

function taskStatusLabel(status) {
  return t(taskStatusKey(status));
}

/* ---------- حالة الحاسوب ---------- */
function parseStatus(data) {
  if (!data || typeof data !== 'object') throw discError('bad_shape', t('err_pc_shape'));
  var disk = null;
  if (data.disk && typeof data.disk === 'object') {
    disk = {
      total_gb: Number(data.disk.total_gb) || 0,
      free_gb: Number(data.disk.free_gb) || 0
    };
  }
  return {
    app: String(data.app || ''), version: String(data.version || ''),
    os: String(data.os || ''), platform: String(data.platform || ''),
    hostname: String(data.hostname || ''), home: String(data.home || ''),
    uptime_s: Number(data.uptime_s) || 0,
    disk: disk,
    ram_mb: (typeof data.ram_mb === 'number') ? data.ram_mb : null
  };
}

/* مدّة تشغيل مقروءة: 0:00:59 / 1:01:01 / 1d 1:01:01 (أرقام محايدة اللغة) */
function formatUptime(seconds) {
  var s = Math.floor(Number(seconds) || 0);
  if (s < 0) s = 0;
  var d = Math.floor(s / 86400);
  s -= d * 86400;
  var h = Math.floor(s / 3600);
  s -= h * 3600;
  var m = Math.floor(s / 60);
  var sec = s - m * 60;
  function p2(n) { return (n < 10 ? '0' : '') + n; }
  var core = h + ':' + p2(m) + ':' + p2(sec);
  return d > 0 ? d + 'd ' + core : core;
}

function formatSize(bytes) {
  var n = Number(bytes);
  if (bytes == null || isNaN(n) || n < 0) return '';
  if (n < 1024) return t('size_bytes', { n: Math.round(n) });
  if (n < 1024 * 1024) return t('size_kb', { n: Math.round(n / 102.4) / 10 });
  return t('size_mb', { n: Math.round(n / 10485.76) / 100 });
}

/* ---------- الملفّات ---------- */
function parseFiles(data) {
  if (!data || typeof data !== 'object' || !Array.isArray(data.entries)) {
    throw discError('bad_shape', t('err_pc_shape'));
  }
  var entries = [];
  data.entries.forEach(function (e) {
    if (e && typeof e === 'object' && e.name != null && String(e.name) !== '') {
      entries.push({
        name: String(e.name),
        kind: e.kind === 'dir' ? 'dir' : 'file',
        size: (typeof e.size === 'number') ? e.size : null
      });
    }
  });
  return {
    path: String(data.path || ''),
    parent: data.parent == null ? null : String(data.parent),
    entries: entries
  };
}

/* وصل مسار مجلد باسم عنصر بفاصل المنصّة الظاهر في المسار نفسه */
function joinRemotePath(dir, name) {
  var d = String(dir == null ? '' : dir);
  var n = String(name == null ? '' : name);
  if (!d) return n;
  var sep = d.indexOf('\\') >= 0 ? '\\' : '/';
  return d.replace(/[\\/]+$/, '') + sep + n;
}

function parseFileDownload(data) {
  if (!data || typeof data !== 'object' || typeof data.content_b64 !== 'string') {
    throw discError('bad_shape', t('err_pc_shape'));
  }
  return {
    name: String(data.name || ''),
    size: (typeof data.size === 'number') ? data.size : null,
    content_b64: data.content_b64
  };
}

/* ---------- التشغيل والفتح والطاقة ---------- */
function runBody(command) {
  return { command: String(command == null ? '' : command) };
}

function parseRunResult(data) {
  if (!data || typeof data !== 'object') throw discError('bad_shape', t('err_pc_shape'));
  return {
    exit: (typeof data.exit === 'number') ? data.exit : null,
    stdout: String(data.stdout == null ? '' : data.stdout),
    stderr: String(data.stderr == null ? '' : data.stderr),
    timed_out: data.timed_out === true
  };
}

function openBody(target) {
  return { target: String(target == null ? '' : target) };
}

var POWER_ACTIONS = ['shutdown', 'restart', 'lock', 'sleep', 'logoff'];

function powerBody(action) {
  return { action: POWER_ACTIONS.indexOf(action) >= 0 ? action : 'shutdown' };
}

function parsePower(data) {
  if (!data || typeof data !== 'object') throw discError('bad_shape', t('err_pc_shape'));
  return {
    ok: data.ok === true,
    scheduled_in_s: (typeof data.scheduled_in_s === 'number') ? data.scheduled_in_s : null
  };
}

/* ---------- لقطة الشاشة ---------- */
function parseScreenshot(data) {
  if (!data || typeof data !== 'object'
      || typeof data.image_b64 !== 'string' || !data.image_b64) {
    throw discError('bad_shape', t('err_pc_shape'));
  }
  return { image_b64: data.image_b64, format: String(data.format || 'png') };
}

function screenshotDataUri(shot) {
  var fmt = String((shot && shot.format) || 'png')
    .toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!fmt) fmt = 'png';
  return 'data:image/' + fmt + ';base64,' + (shot ? shot.image_b64 : '');
}

/* ---------- الطباعة والرفع والحافظة ---------- */
function printBody(path, printer) {
  var body = { path: String(path == null ? '' : path) };
  var p = String(printer == null ? '' : printer).trim();
  if (p) body.printer = p;
  return body;
}

function parsePrinters(data) {
  var items = (data && typeof data === 'object') ? data.printers : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_pc_shape'));
  var printers = [];
  items.forEach(function (p) {
    if (p && typeof p === 'object' && p.name != null && String(p.name) !== '') {
      printers.push({ name: String(p.name), is_default: p.is_default === true });
    }
  });
  return printers;
}

/* جسم الرفع: يفصل حمولة Base64 عن بادئة data: URL إن وُجدت */
function uploadBody(path, dataUrl) {
  var text = String(dataUrl == null ? '' : dataUrl);
  var comma = text.indexOf(',');
  var payload = comma >= 0 ? text.slice(comma + 1) : text;
  return {
    path: String(path == null ? '' : path),
    content_b64: payload.replace(/\s+/g, '')
  };
}

function clipboardBody(text) {
  return { text: String(text == null ? '' : text) };
}

function parseClipboard(data) {
  if (!data || typeof data !== 'object' || typeof data.text !== 'string') {
    throw discError('bad_shape', t('err_pc_shape'));
  }
  return data.text;
}

/* ---------- الصوت والنوافذ والعمليات ---------- */
function volumeBody(action) {
  var known = ['up', 'down', 'mute'];
  return { action: known.indexOf(action) >= 0 ? action : 'mute' };
}

function parseWindows(data) {
  var items = (data && typeof data === 'object') ? data.windows : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_pc_shape'));
  var windows = [];
  items.forEach(function (w) {
    if (w && typeof w === 'object' && w.id != null) {
      windows.push({ id: w.id, title: String(w.title || '') });
    }
  });
  return windows;
}

function windowBody(id, action) {
  var known = ['focus', 'minimize', 'maximize', 'close'];
  return {
    id: coerceNumericId(id),
    action: known.indexOf(action) >= 0 ? action : 'focus'
  };
}

function parseProcesses(data) {
  var items = (data && typeof data === 'object') ? data.processes : null;
  if (!Array.isArray(items)) throw discError('bad_shape', t('err_pc_shape'));
  var processes = [];
  items.forEach(function (p) {
    if (p && typeof p === 'object' && p.pid != null && !isNaN(Number(p.pid))) {
      processes.push({
        pid: Number(p.pid),
        name: String(p.name || ''),
        mem_mb: (typeof p.mem_mb === 'number') ? p.mem_mb : null
      });
    }
  });
  return processes;
}

function killBody(pid) {
  return { pid: coerceNumericId(pid) };
}

/* ---------- الشاشة الحية والإدخال عن بعد (v3.3) ----------
 * عقد الخادم:
 *   GET  /api/screen/stream?token=&w=&q=&fps= → بثّ MJPEG يُوضَع في <img>
 *   POST /api/input {type, x, y, ...}         → {ok} حدث إدخال واحد
 * الإحداثيات طبيعية 0..1 نسبةً إلى شاشة الحاسوب. */
var PC_INPUT_TIMEOUT_MS = 15000;

/* قصّ قيمة إلى المجال 0..1 (غير الرقمي → 0) */
function clamp01(n) {
  var v = Number(n);
  if (isNaN(v)) return 0;
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/* رابط بثّ الشاشة من إعدادات الاتصال: الرمز في الاستعلام لأن عنصر
 * <img> لا يستطيع إرسال ترويسة X-Krouchi-Token — مع ترميزه كاملاً. */
function screenStreamUrl(pc, opts) {
  opts = opts || {};
  var w = Number(opts.w) || 1280;
  var q = Number(opts.q) || 60;
  var fps = Number(opts.fps) || 10;
  return pcBaseUrl(pc) + '/api/screen/stream?token='
    + encodeURIComponent(normalizePcConfig(pc).token)
    + '&w=' + encodeURIComponent(w)
    + '&q=' + encodeURIComponent(q)
    + '&fps=' + encodeURIComponent(fps);
}

/* نقطة لمس/فأرة على الصورة → إحداثيات طبيعية 0..1 نسبةً إلى مستطيلها */
function normPoint(clientX, clientY, rect) {
  if (!rect || !(rect.width > 0) || !(rect.height > 0)) return { x: 0, y: 0 };
  return {
    x: clamp01((Number(clientX) - rect.left) / rect.width),
    y: clamp01((Number(clientY) - rect.top) / rect.height)
  };
}

function inputMouseBody(type, point, button) {
  var known = ['mouse_move', 'mouse_down', 'mouse_up'];
  var p = point || {};
  return {
    type: known.indexOf(type) >= 0 ? type : 'mouse_move',
    x: clamp01(p.x), y: clamp01(p.y),
    button: (button === 'right' || button === 'middle') ? button : 'left'
  };
}

function inputWheelBody(point, delta) {
  var p = point || {};
  return {
    type: 'wheel',
    x: clamp01(p.x), y: clamp01(p.y),
    delta: Math.round(Number(delta) || 0)
  };
}

function inputKeyBody(key) {
  return { type: 'key', key: String(key == null ? '' : key) };
}

function inputTextBody(text) {
  return { type: 'text', text: String(text == null ? '' : text) };
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
    PC_RUN_TIMEOUT_MS: PC_RUN_TIMEOUT_MS, ERR_PC_DENIED: ERR_PC_DENIED,
    normalizeBaseUrl: normalizeBaseUrl, deriveName: deriveName,
    sanitizeName: sanitizeName, parseModelsOpenAI: parseModelsOpenAI,
    httpErrorFor: httpErrorFor, buildChatBody: buildChatBody,
    parseChatReply: parseChatReply,
    httpRequest: httpRequest, fetchTransport: fetchTransport,
    discoverModels: discoverModels, sendChat: sendChat,
    defaultPcConfig: defaultPcConfig, normalizePcConfig: normalizePcConfig,
    normalizeMac: normalizeMac,
    loadPcConfig: loadPcConfig, savePcConfig: savePcConfig,
    pcBaseUrl: pcBaseUrl, pcHeaders: pcHeaders, buildPcRequest: buildPcRequest,
    pcChatBody: pcChatBody, pcDecisionBody: pcDecisionBody, pcRequest: pcRequest,
    parsePing: parsePing, parsePcBots: parsePcBots,
    parsePcHistory: parsePcHistory, parsePcApprovals: parsePcApprovals,
    parsePcChatReply: parsePcChatReply, createPoller: createPoller,
    coerceNumericId: coerceNumericId,
    TASK_STATUSES: TASK_STATUSES, taskBody: taskBody,
    parseTasks: parseTasks, parseTaskDetail: parseTaskDetail,
    taskStatusKey: taskStatusKey, taskStatusLabel: taskStatusLabel,
    parseStatus: parseStatus, formatUptime: formatUptime,
    formatSize: formatSize, parseFiles: parseFiles,
    joinRemotePath: joinRemotePath, parseFileDownload: parseFileDownload,
    runBody: runBody, parseRunResult: parseRunResult, openBody: openBody,
    POWER_ACTIONS: POWER_ACTIONS, powerBody: powerBody,
    parsePower: parsePower, parseScreenshot: parseScreenshot,
    screenshotDataUri: screenshotDataUri,
    printBody: printBody, parsePrinters: parsePrinters,
    uploadBody: uploadBody, clipboardBody: clipboardBody,
    parseClipboard: parseClipboard,
    volumeBody: volumeBody, parseWindows: parseWindows,
    windowBody: windowBody, parseProcesses: parseProcesses,
    killBody: killBody,
    PC_INPUT_TIMEOUT_MS: PC_INPUT_TIMEOUT_MS,
    screenStreamUrl: screenStreamUrl, normPoint: normPoint,
    inputMouseBody: inputMouseBody, inputWheelBody: inputWheelBody,
    inputKeyBody: inputKeyBody, inputTextBody: inputTextBody
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
    renderPcTasks(lastPcTasks);
    if (currentTaskDetail && currentTaskDetail.title != null) renderTaskDetail();
    renderPcStatus();
    if (lastPcFiles) renderPcFiles();
    renderPcPrinters();
    if (pcWindowsLoaded) renderPcWindows();
    if (pcProcessesLoaded) renderPcProcesses();
    renderPowerButtons();
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
  el('pcWakeBtn').addEventListener('click', onPcWake);
  el('pc-chat-send').addEventListener('click', onPcChatSend);
  el('pc-chat-back').addEventListener('click', closePcChat);
  el('task-create').addEventListener('click', onTaskCreate);
  el('task-back').addEventListener('click', closeTaskDetail);
  el('task-cancel').addEventListener('click', onTaskCancel);
  el('status-refresh').addEventListener('click', function () {
    refreshPcStatus();
    if (pcFilesPath) loadPcFiles(pcFilesPath);
  });
  el('files-up').addEventListener('click', function () {
    if (lastPcFiles && lastPcFiles.parent) loadPcFiles(lastPcFiles.parent);
  });
  el('upload-input').addEventListener('change', onUploadPick);
  el('run-btn').addEventListener('click', onPcRun);
  el('open-btn').addEventListener('click', onPcOpen);
  el('shot-btn').addEventListener('click', onPcScreenshot);
  el('clip-get').addEventListener('click', onClipGet);
  el('clip-set').addEventListener('click', onClipSet);
  el('vol-down').addEventListener('click', function () { onPcVolume('down'); });
  el('vol-mute').addEventListener('click', function () { onPcVolume('mute'); });
  el('vol-up').addEventListener('click', function () { onPcVolume('up'); });
  el('windows-refresh').addEventListener('click', refreshPcWindows);
  el('proc-refresh').addEventListener('click', refreshPcProcesses);
  el('screen-start').addEventListener('click', startPcScreen);
  el('screen-stop').addEventListener('click', stopPcScreen);
  el('screen-drag').addEventListener('click', onScreenDragToggle);
  el('screen-wheel-up').addEventListener('click', function () { onScreenWheel(1); });
  el('screen-wheel-down').addEventListener('click', function () { onScreenWheel(-1); });
  el('screen-send-text').addEventListener('click', onScreenSendText);
  var screenImg = el('pcScreenImg');
  screenImg.addEventListener('pointerdown', onScreenPointerDown);
  screenImg.addEventListener('pointermove', onScreenPointerMove);
  screenImg.addEventListener('pointerup', onScreenPointerUp);
  screenImg.addEventListener('pointercancel', onScreenPointerCancel);
  screenImg.addEventListener('error', onScreenImgError);
  screenImg.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  document.querySelectorAll('[data-screen-key]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      onScreenKey(btn.getAttribute('data-screen-key'));
    });
  });
  POWER_ACTIONS.forEach(function (a) {
    el(powerBtnId(a)).addEventListener('click', function () { onPcPower(a); });
  });
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
      startPcTasksPolling();
    }
  } else {
    stopPcApprovalsPolling();
    stopPcTasksPolling();
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
  el('pcMac').value = cfg.mac || '';
}

function readPcForm() {
  return normalizePcConfig({
    host: el('pc-host').value,
    port: el('pc-port').value,
    token: el('pc-token').value,
    mac: el('pcMac').value
  });
}

function setPcStatus(msg, ok) {
  var box = el('pc-status');
  box.textContent = msg;
  box.className = 'status ' + (ok === true ? 'ok' : ok === false ? 'err' : '');
}

/* إيقاظ الحاسوب المنطفئ (Wake-on-LAN): يُقرأ العنوان من الحقل أو من
 * الإعدادات المحفوظة، يُتحقق منه ويُحفظ بصيغته القانونية، ثم يُرسل عبر
 * الجسر الأصيل في تطبيق الأندرويد؛ بلا جسر (متصفح/آيفون) تُعرض ملاحظة */
function onPcWake() {
  var mac = normalizeMac(el('pcMac').value) || normalizeMac(loadPcConfig().mac);
  if (!mac) {
    setPcStatus(t('pc_wake_bad_mac'), false);
    return;
  }
  el('pcMac').value = mac;
  var cfg = readPcForm();
  cfg.mac = mac;
  savePcConfig(cfg);
  if (typeof window !== 'undefined' && window.KrouchiBridge &&
      typeof window.KrouchiBridge.wol === 'function') {
    window.KrouchiBridge.wol(mac);
    setPcStatus(t('pc_wake_sent'), true);
  } else {
    setPcStatus(t('pc_wake_unsupported'), false);
  }
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
    startPcTasksPolling();
    refreshPcStatus();
    refreshPcPrinters();
    renderPowerButtons();
  }).catch(function (err) {
    btn.disabled = false;
    btn.textContent = t('btn_connect');
    pcConnected = false;
    el('pc-connected').style.display = 'none';
    stopPcApprovalsPolling();
    stopPcTasksPolling();
    stopPcScreen();
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
  fillTaskBotPicker();
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
/* ================= المهام (v3.2) ================= */
var pcTasksPoller = null;
var lastPcTasks = [];
var currentTaskDetail = null;

function setBoxStatus(id, msg, ok) {
  var box = el(id);
  if (!box) return;
  box.textContent = msg;
  box.className = 'status ' + (ok === true ? 'ok' : ok === false ? 'err' : '');
}

function taskBadgeClass(status) {
  if (status === 'done') return 'badge ok';
  if (status === 'failed' || status === 'waiting_approval') return 'badge err';
  return 'badge';
}

function fillTaskBotPicker() {
  var sel = el('task-bot');
  if (!sel) return;
  var current = sel.value;
  sel.innerHTML = lastPcBots.map(function (b) {
    return '<option value="' + escapeHtml(b.id) + '">' + escapeHtml(b.name) + '</option>';
  }).join('');
  if (current && lastPcBots.some(function (b) { return b.id === current; })) {
    sel.value = current;
  }
}

function refreshPcTasks() {
  if (!pcConnected || !pcCfg) return;
  pcRequest(pcCfg, 'GET', '/api/tasks').then(function (data) {
    renderPcTasks(parseTasks(data));
  }).catch(function () { /* خطأ عابر: تبقى القائمة كما هي */ });
}

function startPcTasksPolling() {
  if (pcTasksPoller || !pcConnected || !pcCfg) return;
  pcTasksPoller = createPoller({
    intervalMs: 4000,
    task: function () {
      return pcRequest(pcCfg, 'GET', '/api/tasks')
        .then(function (data) {
          renderPcTasks(parseTasks(data));
          if (currentTaskDetail) {
            return refreshTaskDetail(currentTaskDetail.id, true);
          }
          return null;
        });
    },
    onResult: function () {},
    onError: function () { /* خطأ عابر: نبقى على آخر حالة */ }
  });
  pcTasksPoller.start();
}

function stopPcTasksPolling() {
  if (pcTasksPoller) {
    pcTasksPoller.stop();
    pcTasksPoller = null;
  }
}

function renderPcTasks(tasks) {
  lastPcTasks = tasks || [];
  var box = el('pc-tasks-list');
  if (!box) return;
  if (!lastPcTasks.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('tasks_none')) + '</p>';
    return;
  }
  box.innerHTML = lastPcTasks.map(function (tk) {
    return '<div class="card"><div class="card-title">' + escapeHtml(tk.title) + '</div>'
      + '<div class="muted">'
      + escapeHtml(t('task_bot_line', { name: tk.bot_name || t('approval_bot_fallback') }))
      + '</div>'
      + (tk.created_at
        ? '<div class="muted">' + escapeHtml(tk.created_at) + '</div>' : '')
      + '<div><span class="' + taskBadgeClass(tk.status) + '">'
      + escapeHtml(taskStatusLabel(tk.status)) + '</span></div>'
      + '<button data-task-open="' + escapeHtml(tk.id) + '">'
      + escapeHtml(t('btn_details')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-task-open]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      openTaskDetail(btn.getAttribute('data-task-open'));
    });
  });
}

function onTaskCreate() {
  if (!pcCfg) return;
  var botId = el('task-bot').value;
  var title = el('task-title').value.trim();
  var prompt = el('task-prompt').value.trim();
  if (!botId) { setBoxStatus('task-status', t('task_err_bot'), false); return; }
  if (!title) { setBoxStatus('task-status', t('task_err_title'), false); return; }
  if (!prompt) { setBoxStatus('task-status', t('task_err_prompt'), false); return; }
  var btn = el('task-create');
  btn.disabled = true;
  pcRequest(pcCfg, 'POST', '/api/tasks', taskBody(botId, title, prompt))
    .then(function () {
      btn.disabled = false;
      setBoxStatus('task-status', t('task_created', { title: title }), true);
      el('task-title').value = '';
      el('task-prompt').value = '';
      if (pcTasksPoller) pcTasksPoller.tick();
      else refreshPcTasks();
    }).catch(function (err) {
      btn.disabled = false;
      setBoxStatus('task-status', err.message || String(err), false);
    });
}

function openTaskDetail(id) {
  currentTaskDetail = { id: String(id) };
  el('pc-tasks-wrap').style.display = 'none';
  el('pc-task-detail').style.display = 'block';
  refreshTaskDetail(String(id), false);
}

function closeTaskDetail() {
  currentTaskDetail = null;
  el('pc-task-detail').style.display = 'none';
  el('pc-tasks-wrap').style.display = 'block';
  refreshPcTasks();
}

function refreshTaskDetail(id, silent) {
  if (!pcCfg) return Promise.resolve();
  return pcRequest(pcCfg, 'GET', '/api/tasks/' + encodeURIComponent(id))
    .then(function (data) {
      currentTaskDetail = parseTaskDetail(data);
      renderTaskDetail();
    }).catch(function (err) {
      if (!silent) toast(err.message || String(err));
    });
}

function renderTaskDetail() {
  var tk = currentTaskDetail;
  if (!tk || tk.title == null) return;
  el('task-detail-title').textContent = tk.title;
  el('task-detail-meta').innerHTML =
    '<span class="' + taskBadgeClass(tk.status) + '">'
    + escapeHtml(taskStatusLabel(tk.status)) + '</span>'
    + (tk.bot_name
      ? '<div class="muted">'
        + escapeHtml(t('task_bot_line', { name: tk.bot_name })) + '</div>' : '')
    + (tk.created_at
      ? '<div class="muted">' + escapeHtml(tk.created_at) + '</div>' : '');
  var html = '<label>' + escapeHtml(t('task_detail_prompt')) + '</label>'
    + '<div class="card"><div style="white-space:pre-wrap">'
    + escapeHtml(tk.prompt) + '</div></div>';
  if (tk.result) {
    html += '<label>' + escapeHtml(t('task_detail_result')) + '</label>'
      + '<div class="card"><div style="white-space:pre-wrap">'
      + escapeHtml(tk.result) + '</div></div>';
  }
  if (tk.error) {
    html += '<label>' + escapeHtml(t('task_detail_error')) + '</label>'
      + '<div class="card"><div style="white-space:pre-wrap;color:#b71c1c">'
      + escapeHtml(tk.error) + '</div></div>';
  }
  html += '<label>' + escapeHtml(t('task_detail_log')) + '</label>';
  if (tk.log && tk.log.length) {
    html += tk.log.map(function (line) {
      return '<div class="logline">'
        + escapeHtml((line.ts ? line.ts + ' — ' : '') + line.text) + '</div>';
    }).join('');
  } else {
    html += '<p class="muted">' + escapeHtml(t('task_log_empty')) + '</p>';
  }
  el('task-detail-body').innerHTML = html;
  var cancellable = ['queued', 'running', 'waiting_approval']
    .indexOf(tk.status) >= 0;
  el('task-cancel').style.display = cancellable ? '' : 'none';
}

function onTaskCancel() {
  if (!currentTaskDetail || !pcCfg) return;
  var id = currentTaskDetail.id;
  pcRequest(pcCfg, 'POST', '/api/tasks/' + encodeURIComponent(id) + '/cancel', {})
    .then(function () {
      toast(t('toast_task_cancelled'));
      refreshTaskDetail(id, true);
      refreshPcTasks();
    }).catch(function (err) {
      toast(err.message || String(err));
    });
}

/* ================= التحكّم بالحاسوب (v3.2) ================= */
var lastPcStatus = null;
var lastPcFiles = null;
var pcFilesPath = '';
var lastPcPrinters = [];
var lastPcWindows = [];
var pcWindowsLoaded = false;
var lastPcProcesses = [];
var pcProcessesLoaded = false;
var powerArmAction = null;
var powerArmTimer = null;

/* ---------- الحالة ---------- */
function refreshPcStatus() {
  if (!pcConnected || !pcCfg) return;
  pcRequest(pcCfg, 'GET', '/api/status').then(function (data) {
    lastPcStatus = parseStatus(data);
    renderPcStatus();
    if (!pcFilesPath && lastPcStatus.home) loadPcFiles(lastPcStatus.home);
  }).catch(function () { /* خطأ عابر */ });
}

function renderPcStatus() {
  var box = el('pc-status-fields');
  if (!box) return;
  var st = lastPcStatus;
  if (!st) { box.innerHTML = ''; return; }
  function row(key, value) {
    return '<div class="muted">' + escapeHtml(t(key)) + '</div>'
      + '<div>' + escapeHtml(value) + '</div>';
  }
  var html = '';
  if (st.hostname) html += row('status_hostname', st.hostname);
  if (st.os) html += row('status_os', st.os);
  if (st.platform) html += row('status_platform', st.platform);
  if (st.version) html += row('status_version', st.version);
  html += row('status_uptime', formatUptime(st.uptime_s));
  if (st.disk) {
    html += row('status_disk', t('status_disk_value',
      { free: st.disk.free_gb, total: st.disk.total_gb }));
  }
  if (st.ram_mb != null) {
    html += row('status_ram', t('status_ram_value', { mb: st.ram_mb }));
  }
  box.innerHTML = html;
}

/* ---------- الملفّات ---------- */
function loadPcFiles(path) {
  if (!pcCfg || path == null || path === '') return;
  pcRequest(pcCfg, 'GET', '/api/files?path=' + encodeURIComponent(path))
    .then(function (data) {
      lastPcFiles = parseFiles(data);
      pcFilesPath = lastPcFiles.path || path;
      renderPcFiles();
    }).catch(function (err) {
      setBoxStatus('files-status', err.message || String(err), false);
    });
}

function renderPcFiles() {
  var box = el('files-list');
  if (!box) return;
  el('files-path').textContent = pcFilesPath || '';
  el('files-up').style.display =
    (lastPcFiles && lastPcFiles.parent) ? '' : 'none';
  if (!lastPcFiles) { box.innerHTML = ''; return; }
  if (!lastPcFiles.entries.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('files_empty')) + '</p>';
    return;
  }
  box.innerHTML = lastPcFiles.entries.map(function (e, i) {
    if (e.kind === 'dir') {
      return '<div class="card"><div class="card-title">📁 '
        + escapeHtml(e.name) + '</div>'
        + '<button data-dir-idx="' + i + '">'
        + escapeHtml(t('btn_open_folder')) + '</button></div>';
    }
    return '<div class="card"><div class="card-title">📄 '
      + escapeHtml(e.name) + '</div>'
      + (e.size != null
        ? '<div class="muted">' + escapeHtml(formatSize(e.size)) + '</div>' : '')
      + '<button data-dl-idx="' + i + '">'
      + escapeHtml(t('btn_download')) + '</button> '
      + '<button data-print-idx="' + i + '">'
      + escapeHtml(t('btn_print')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-dir-idx]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var e = lastPcFiles.entries[Number(btn.getAttribute('data-dir-idx'))];
      if (e) loadPcFiles(joinRemotePath(pcFilesPath, e.name));
    });
  });
  box.querySelectorAll('[data-dl-idx]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var e = lastPcFiles.entries[Number(btn.getAttribute('data-dl-idx'))];
      if (e) downloadPcFile(e);
    });
  });
  box.querySelectorAll('[data-print-idx]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var e = lastPcFiles.entries[Number(btn.getAttribute('data-print-idx'))];
      if (e) printPcFile(e);
    });
  });
}

function saveDownload(name, contentB64) {
  try {
    var bin = atob(contentB64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var blob = new Blob([bytes]);
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name || 'file';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 5000);
  } catch (e) { /* بيئة بلا تنزيلات: نتجاهل بصمت */ }
}

function downloadPcFile(entry) {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'GET',
    '/api/file?path=' + encodeURIComponent(joinRemotePath(pcFilesPath, entry.name)))
    .then(function (data) {
      var file = parseFileDownload(data);
      saveDownload(file.name || entry.name, file.content_b64);
      toast(t('toast_download_started', { name: file.name || entry.name }));
    }).catch(function (err) {
      setBoxStatus('files-status', err.message || String(err), false);
    });
}

function printPcFile(entry) {
  if (!pcCfg) return;
  var printer = el('printer-select').value || '';
  pcRequest(pcCfg, 'POST', '/api/print',
    printBody(joinRemotePath(pcFilesPath, entry.name), printer))
    .then(function () {
      toast(t('toast_print_sent', { name: entry.name }));
    }).catch(function (err) {
      setBoxStatus('files-status', err.message || String(err), false);
    });
}

/* ---------- الرفع ---------- */
function onUploadPick() {
  var input = el('upload-input');
  var file = input.files && input.files[0];
  if (!file || !pcCfg) return;
  setBoxStatus('upload-status', t('upload_sending', { name: file.name }), null);
  var reader = new FileReader();
  reader.onload = function () {
    var body = uploadBody(
      joinRemotePath(pcFilesPath, file.name), String(reader.result || ''));
    input.value = '';
    pcRequest(pcCfg, 'POST', '/api/upload', body)
      .then(function (data) {
        var size = (data && typeof data.size === 'number')
          ? formatSize(data.size) : '';
        setBoxStatus('upload-status',
          t('upload_done', { name: file.name, size: size }), true);
        if (pcFilesPath) loadPcFiles(pcFilesPath);
      }).catch(function (err) {
        setBoxStatus('upload-status', err.message || String(err), false);
      });
  };
  reader.onerror = function () {
    input.value = '';
    setBoxStatus('upload-status', String(reader.error || 'error'), false);
  };
  reader.readAsDataURL(file);
}

/* ---------- الطابعات ---------- */
function refreshPcPrinters() {
  if (!pcConnected || !pcCfg) return;
  pcRequest(pcCfg, 'GET', '/api/printers').then(function (data) {
    lastPcPrinters = parsePrinters(data);
    renderPcPrinters();
  }).catch(function () { /* خطأ عابر */ });
}

function renderPcPrinters() {
  var sel = el('printer-select');
  if (!sel) return;
  var current = sel.value;
  sel.innerHTML = '<option value="">' + escapeHtml(t('printer_auto')) + '</option>'
    + lastPcPrinters.map(function (p) {
      return '<option value="' + escapeHtml(p.name) + '">'
        + escapeHtml(p.name)
        + (p.is_default ? escapeHtml(t('printer_default_suffix')) : '')
        + '</option>';
    }).join('');
  sel.value = current || '';
  el('printers-list').innerHTML = lastPcPrinters.length ? ''
    : '<p class="muted">' + escapeHtml(t('printers_none')) + '</p>';
}

/* ---------- تشغيل أمر / فتح ---------- */
function onPcRun() {
  if (!pcCfg) return;
  var cmd = el('run-input').value.trim();
  if (!cmd) return;
  var out = el('run-output');
  out.style.display = 'block';
  out.textContent = t('run_running');
  var btn = el('run-btn');
  btn.disabled = true;
  pcRequest(pcCfg, 'POST', '/api/run', runBody(cmd), PC_RUN_TIMEOUT_MS)
    .then(function (data) {
      btn.disabled = false;
      var r = parseRunResult(data);
      var lines = [r.timed_out
        ? t('run_timed_out')
        : t('run_exit', { code: r.exit == null ? t('unknown_mark') : r.exit })];
      if (r.stdout) lines.push(r.stdout);
      if (r.stderr) lines.push(r.stderr);
      out.textContent = lines.join('\n');
    }).catch(function (err) {
      btn.disabled = false;
      out.textContent = err.message || String(err);
    });
}

function onPcOpen() {
  if (!pcCfg) return;
  var target = el('open-input').value.trim();
  if (!target) return;
  pcRequest(pcCfg, 'POST', '/api/open', openBody(target))
    .then(function () {
      toast(t('toast_opened'));
      setBoxStatus('open-status', '', null);
    }).catch(function (err) {
      setBoxStatus('open-status', err.message || String(err), false);
    });
}

/* ---------- لقطة الشاشة ---------- */
function onPcScreenshot() {
  if (!pcCfg) return;
  setBoxStatus('shot-status', '', null);
  pcRequest(pcCfg, 'GET', '/api/screenshot')
    .then(function (data) {
      var img = el('shot-img');
      img.src = screenshotDataUri(parseScreenshot(data));
      img.style.display = 'block';
    }).catch(function (err) {
      setBoxStatus('shot-status', err.message || String(err), false);
    });
}

/* ---------- الحافظة ---------- */
function onClipGet() {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'GET', '/api/clipboard')
    .then(function (data) {
      var text = parseClipboard(data);
      el('clip-text').value = text;
      setBoxStatus('clip-status', text ? '' : t('clip_empty'), text ? null : false);
    }).catch(function (err) {
      setBoxStatus('clip-status', err.message || String(err), false);
    });
}

function onClipSet() {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'POST', '/api/clipboard', clipboardBody(el('clip-text').value))
    .then(function () {
      toast(t('toast_clip_sent'));
    }).catch(function (err) {
      setBoxStatus('clip-status', err.message || String(err), false);
    });
}

/* ---------- الصوت ---------- */
function onPcVolume(action) {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'POST', '/api/volume', volumeBody(action))
    .then(function () {
      toast(t('toast_volume'));
    }).catch(function (err) {
      toast(err.message || String(err));
    });
}

/* ---------- النوافذ ---------- */
function refreshPcWindows() {
  if (!pcConnected || !pcCfg) return;
  pcRequest(pcCfg, 'GET', '/api/windows')
    .then(function (data) {
      lastPcWindows = parseWindows(data);
      pcWindowsLoaded = true;
      renderPcWindows();
    }).catch(function (err) {
      el('windows-list').innerHTML = '<p class="muted">'
        + escapeHtml(err.message || String(err)) + '</p>';
    });
}

function renderPcWindows() {
  var box = el('windows-list');
  if (!box) return;
  if (!lastPcWindows.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('windows_none')) + '</p>';
    return;
  }
  box.innerHTML = lastPcWindows.map(function (w, i) {
    return '<div class="card"><div class="card-title">' + escapeHtml(w.title)
      + '</div>'
      + '<button data-win-idx="' + i + '" data-win-act="focus">'
      + escapeHtml(t('btn_win_focus')) + '</button> '
      + '<button data-win-idx="' + i + '" data-win-act="minimize">'
      + escapeHtml(t('btn_win_minimize')) + '</button> '
      + '<button data-win-idx="' + i + '" data-win-act="maximize">'
      + escapeHtml(t('btn_win_maximize')) + '</button> '
      + '<button class="danger" data-win-idx="' + i + '" data-win-act="close">'
      + escapeHtml(t('btn_win_close')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-win-act]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var w = lastPcWindows[Number(btn.getAttribute('data-win-idx'))];
      if (w) onPcWindowAction(w.id, btn.getAttribute('data-win-act'));
    });
  });
}

function onPcWindowAction(id, action) {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'POST', '/api/window', windowBody(id, action))
    .then(function () {
      toast(t('toast_window_action'));
      refreshPcWindows();
    }).catch(function (err) {
      toast(err.message || String(err));
    });
}

/* ---------- العمليات ---------- */
function refreshPcProcesses() {
  if (!pcConnected || !pcCfg) return;
  pcRequest(pcCfg, 'GET', '/api/processes')
    .then(function (data) {
      lastPcProcesses = parseProcesses(data);
      pcProcessesLoaded = true;
      renderPcProcesses();
    }).catch(function (err) {
      el('proc-list').innerHTML = '<p class="muted">'
        + escapeHtml(err.message || String(err)) + '</p>';
    });
}

function renderPcProcesses() {
  var box = el('proc-list');
  if (!box) return;
  if (!lastPcProcesses.length) {
    box.innerHTML = '<p class="muted">' + escapeHtml(t('processes_none')) + '</p>';
    return;
  }
  box.innerHTML = lastPcProcesses.map(function (p, i) {
    var mem = p.mem_mb != null ? formatSize(p.mem_mb * 1048576) : '';
    return '<div class="card"><div class="card-title">' + escapeHtml(p.name)
      + '</div>'
      + '<div class="muted">'
      + escapeHtml(t('proc_line', { pid: p.pid, mem: mem })) + '</div>'
      + '<button class="danger" data-proc-idx="' + i + '">'
      + escapeHtml(t('btn_kill')) + '</button></div>';
  }).join('');
  box.querySelectorAll('[data-proc-idx]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var p = lastPcProcesses[Number(btn.getAttribute('data-proc-idx'))];
      if (p) onPcKill(p.pid);
    });
  });
}

function onPcKill(pid) {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'POST', '/api/process/kill', killBody(pid))
    .then(function () {
      toast(t('toast_kill_sent'));
      refreshPcProcesses();
    }).catch(function (err) {
      toast(err.message || String(err));
    });
}

/* ---------- الطاقة (تأكيد مزدوج داخل الواجهة) ---------- */
function powerBtnId(action) { return 'power-' + action; }

function renderPowerButtons() {
  POWER_ACTIONS.forEach(function (a) {
    var btn = el(powerBtnId(a));
    if (!btn) return;
    var armed = powerArmAction === a;
    btn.textContent = armed ? t('btn_confirm_action') : t('btn_' + a);
    btn.classList.toggle('armed', armed);
  });
}

function onPcPower(action) {
  if (!pcCfg) return;
  if (powerArmAction !== action) {
    /* الضغطة الأولى تُجهِّز، والثانية خلال 4 ثوانٍ تُرسل */
    powerArmAction = action;
    renderPowerButtons();
    if (powerArmTimer) clearTimeout(powerArmTimer);
    powerArmTimer = setTimeout(function () {
      powerArmAction = null;
      renderPowerButtons();
    }, 4000);
    return;
  }
  if (powerArmTimer) clearTimeout(powerArmTimer);
  powerArmAction = null;
  renderPowerButtons();
  pcRequest(pcCfg, 'POST', '/api/power', powerBody(action))
    .then(function (data) {
      var r = parsePower(data);
      setBoxStatus('power-status',
        r.scheduled_in_s != null
          ? t('power_scheduled', { seconds: r.scheduled_in_s })
          : t('power_done'), true);
    }).catch(function (err) {
      setBoxStatus('power-status', err.message || String(err), false);
    });
}

/* ================= الشاشة الحية والتحكّم باللمس (v3.3) ================= */
var pcScreenOn = false;
var pcScreenDragMode = false;
var pcScreenPtr = null;
var pcScreenInputFailed = false;

function renderScreenButtons() {
  var start = el('screen-start');
  var stop = el('screen-stop');
  if (start) start.style.display = pcScreenOn ? 'none' : '';
  if (stop) stop.style.display = pcScreenOn ? '' : 'none';
}

function startPcScreen() {
  if (!pcCfg) return;
  setBoxStatus('screen-status', '', null);
  pcScreenInputFailed = false;
  var img = el('pcScreenImg');
  img.src = screenStreamUrl(pcCfg, { w: 1280, q: 60, fps: 10 });
  img.style.display = 'block';
  pcScreenOn = true;
  renderScreenButtons();
}

function stopPcScreen() {
  pcScreenOn = false;
  pcScreenPtr = null;
  var img = el('pcScreenImg');
  if (img) {
    img.removeAttribute('src');
    img.style.display = 'none';
  }
  renderScreenButtons();
}

/* فشل تحميل البثّ (رمز خاطئ أو تحكّم معطّل أو نظام لا يدعم البثّ):
 * الصورة لا تصل أبداً — نعود إلى حالة الإيقاف مع ملاحظة. */
function onScreenImgError() {
  if (!pcScreenOn) return;
  stopPcScreen();
  setBoxStatus('screen-status', t('screen_err'), false);
}

/* إرسال حدث إدخال واحد: الفشل لا يقطع التفاعل؛ أول فشل يترك ملاحظة
 * هادئة في سطر الحالة، وأول نجاح بعده يمسحها — بلا إزعاج أثناء السحب. */
function sendPcInput(body) {
  if (!pcCfg) return;
  pcRequest(pcCfg, 'POST', '/api/input', body, PC_INPUT_TIMEOUT_MS)
    .then(function () {
      if (pcScreenInputFailed) {
        pcScreenInputFailed = false;
        setBoxStatus('screen-status', '', null);
      }
    })
    .catch(function () {
      if (!pcScreenInputFailed) {
        pcScreenInputFailed = true;
        setBoxStatus('screen-status', t('screen_input_failed'), false);
      }
    });
}

function screenPointFromEvent(e) {
  var img = el('pcScreenImg');
  return normPoint(e.clientX, e.clientY, img.getBoundingClientRect());
}

function onScreenPointerDown(e) {
  if (!pcScreenOn) return;
  e.preventDefault();
  var img = el('pcScreenImg');
  try { img.setPointerCapture(e.pointerId); } catch (err) { /* بيئة بلا أسر للمؤشّر */ }
  var state = {
    id: e.pointerId, startPt: screenPointFromEvent(e), lastPt: null,
    startT: Date.now(), moved: false, longFired: false,
    dragDown: false, lastMoveAt: 0, longTimer: null
  };
  state.lastPt = state.startPt;
  pcScreenPtr = state;
  state.longTimer = setTimeout(function () {
    if (pcScreenPtr === state && !state.moved) {
      state.longFired = true;
      sendPcInput(inputMouseBody('mouse_down', state.startPt, 'right'));
      sendPcInput(inputMouseBody('mouse_up', state.startPt, 'right'));
    }
  }, 500);
}

function onScreenPointerMove(e) {
  var state = pcScreenPtr;
  if (!state || e.pointerId !== state.id || !pcScreenOn) return;
  e.preventDefault();
  var pt = screenPointFromEvent(e);
  state.lastPt = pt;
  var rect = el('pcScreenImg').getBoundingClientRect();
  if (Math.abs((pt.x - state.startPt.x) * rect.width) > 8
      || Math.abs((pt.y - state.startPt.y) * rect.height) > 8) {
    state.moved = true;
  }
  if (!state.moved || state.longFired) return;
  if (pcScreenDragMode && !state.dragDown) {
    state.dragDown = true;
    sendPcInput(inputMouseBody('mouse_down', state.startPt, 'left'));
  }
  var now = Date.now();
  if (now - state.lastMoveAt >= 60) {
    state.lastMoveAt = now;
    sendPcInput(inputMouseBody('mouse_move', pt));
  }
}

function onScreenPointerUp(e) {
  var state = pcScreenPtr;
  if (!state || e.pointerId !== state.id) return;
  pcScreenPtr = null;
  if (state.longTimer) clearTimeout(state.longTimer);
  if (!pcScreenOn) return;
  var pt = screenPointFromEvent(e);
  if (state.dragDown) {
    sendPcInput(inputMouseBody('mouse_move', pt));
    sendPcInput(inputMouseBody('mouse_up', pt, 'left'));
    return;
  }
  if (state.longFired || state.moved) return;
  if (Date.now() - state.startT < 500) {
    /* نقرة قصيرة بلا حركة: نقر أيسر عند نقطة البدء */
    sendPcInput(inputMouseBody('mouse_down', state.startPt, 'left'));
    sendPcInput(inputMouseBody('mouse_up', state.startPt, 'left'));
  }
}

function onScreenPointerCancel(e) {
  var state = pcScreenPtr;
  if (!state || e.pointerId !== state.id) return;
  pcScreenPtr = null;
  if (state.longTimer) clearTimeout(state.longTimer);
  if (state.dragDown) {
    /* لا نترك زرّ الفأرة عالقاً على الحاسوب */
    sendPcInput(inputMouseBody('mouse_up', state.lastPt, 'left'));
  }
}

function onScreenWheel(delta) {
  sendPcInput(inputWheelBody({ x: 0.5, y: 0.5 }, delta));
}

function onScreenDragToggle() {
  pcScreenDragMode = !pcScreenDragMode;
  el('screen-drag').classList.toggle('toggle-on', pcScreenDragMode);
}

function onScreenSendText() {
  var input = el('screen-text');
  var text = input.value;
  if (!text) return;
  sendPcInput(inputTextBody(text));
  input.value = '';
}

function onScreenKey(key) {
  sendPcInput(inputKeyBody(key));
}
