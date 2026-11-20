/* اختبارات وحدة لدوال app.js النقية — تشغيل: node tests_app.js */
'use strict';
const assert = require('assert');
const app = require('./assets/app.js');

let passed = 0;
function ok(name, fn) {
  try { fn(); passed++; console.log('✔ ' + name); }
  catch (e) { console.error('✘ ' + name + ': ' + e.message); process.exitCode = 1; }
}
function throwsKind(fn, kind) {
  try { fn(); } catch (e) { assert.strictEqual(e.kind, kind, 'kind=' + e.kind); return; }
  throw new Error('لم يُرمَ خطأ');
}

/* تطبيع العنوان — نفس صور discovery.py */
ok('بلا مخطط يضيف https و /v1', () =>
  assert.strictEqual(app.normalizeBaseUrl('api.deepseek.com'), 'https://api.deepseek.com/v1'));
ok('شرطة أخيرة تُحذف', () =>
  assert.strictEqual(app.normalizeBaseUrl('https://openrouter.ai/api/v1/'), 'https://openrouter.ai/api/v1'));
ok('بلا /v1 تُضاف', () =>
  assert.strictEqual(app.normalizeBaseUrl('https://api.groq.com/openai'), 'https://api.groq.com/openai/v1'));
ok('لصق chat/completions كاملاً', () =>
  assert.strictEqual(app.normalizeBaseUrl('https://api.z.ai/api/paas/v4/chat/completions'), 'https://api.z.ai/api/paas/v4'));
ok('لصق /models كاملاً', () =>
  assert.strictEqual(app.normalizeBaseUrl('https://integrate.api.nvidia.com/v1/models'), 'https://integrate.api.nvidia.com/v1'));
ok('منفذ محلي يبقى', () =>
  assert.strictEqual(app.normalizeBaseUrl('http://127.0.0.1:31415'), 'http://127.0.0.1:31415/v1'));
ok('v2 تبقى كما هي', () =>
  assert.strictEqual(app.normalizeBaseUrl('https://example.com/api/v2'), 'https://example.com/api/v2'));
ok('فارغ → bad_url', () => throwsKind(() => app.normalizeBaseUrl(''), 'bad_url'));
ok('بلا خادم → bad_url', () => throwsKind(() => app.normalizeBaseUrl('https://'), 'bad_url'));
ok('مخطط غريب → bad_url', () => throwsKind(() => app.normalizeBaseUrl('ftp://x.com'), 'bad_url'));

/* اشتقاق الاسم */
ok('openrouter', () => assert.strictEqual(app.deriveName('https://openrouter.ai/api/v1'), 'openrouter'));
ok('api.deepseek', () => assert.strictEqual(app.deriveName('https://api.deepseek.com/v1'), 'deepseek'));
ok('z.ai قصير', () => assert.strictEqual(app.deriveName('https://api.z.ai/api/paas/v4'), 'z-ai'));
ok('nvidia integrate', () => assert.strictEqual(app.deriveName('https://integrate.api.nvidia.com/v1'), 'nvidia'));

/* تحليل النماذج */
ok('نماذج OpenAI', () =>
  assert.deepStrictEqual(
    app.parseModelsOpenAI({ data: [{ id: 'a' }, { id: 'b' }, { id: 'a' }, { x: 1 }] }),
    ['a', 'b']));
ok('شكل خاطئ → bad_shape', () => throwsKind(() => app.parseModelsOpenAI({ models: [] }), 'bad_shape'));
ok('قائمة فارغة → empty', () => throwsKind(() => app.parseModelsOpenAI({ data: [] }), 'empty'));

/* أخطاء HTTP */
ok('401 → auth', () => throwsKind(() => { throw app.httpErrorFor(401); }, 'auth'));
ok('403 → auth', () => throwsKind(() => { throw app.httpErrorFor(403); }, 'auth'));
ok('500 → http', () => throwsKind(() => { throw app.httpErrorFor(500); }, 'http'));

/* المحادثة */
ok('جسم المحادثة', () =>
  assert.strictEqual(
    app.buildChatBody('m', [{ role: 'user', content: 'hi' }]),
    '{"model":"m","messages":[{"role":"user","content":"hi"}]}'));
ok('تحليل الردّ', () =>
  assert.strictEqual(
    app.parseChatReply({ choices: [{ message: { content: 'أهلاً' } }] }), 'أهلاً'));
ok('ردّ بلا محتوى → bad_shape', () =>
  throwsKind(() => app.parseChatReply({ choices: [] }), 'bad_shape'));

console.log('\n' + passed + ' اختباراً ناجحاً');

/* ================= الوضع المرافق: الاتصال بالحاسوب ================= */

/* تخزين محلي وهمي لاختبار حفظ إعدادات الاتصال */
const __lsStore = {};
global.localStorage = {
  getItem: (k) => (k in __lsStore ? __lsStore[k] : null),
  setItem: (k, v) => { __lsStore[k] = String(v); },
  removeItem: (k) => { delete __lsStore[k]; }
};

let passedPc = 0;
function okPc(name, fn) {
  try { fn(); passedPc++; console.log('✔ [حاسوب] ' + name); }
  catch (e) { console.error('✘ [حاسوب] ' + name + ': ' + e.message); process.exitCode = 1; }
}

/* عنوان أساس الحاسوب */
okPc('IP مجرد بلا منفذ → 8765', () =>
  assert.strictEqual(app.pcBaseUrl({ host: '192.168.1.10' }), 'http://192.168.1.10:8765'));
okPc('منفذ مخصص يُحترم', () =>
  assert.strictEqual(app.pcBaseUrl({ host: '192.168.1.10', port: 9000 }), 'http://192.168.1.10:9000'));
okPc('رابط ملصوق كامل بمنفذه يغلب', () =>
  assert.strictEqual(app.pcBaseUrl({ host: 'http://192.168.1.5:9001/xyz', port: 8765 }), 'http://192.168.1.5:9001'));
okPc('اسم مضيف يعمل', () =>
  assert.strictEqual(app.pcBaseUrl({ host: 'my-pc.local' }), 'http://my-pc.local:8765'));
okPc('منفذ فاسد → الافتراضي', () =>
  assert.strictEqual(app.pcBaseUrl({ host: 'h', port: 99999 }), 'http://h:8765'));
okPc('مضيف فارغ → bad_url', () =>
  throwsKind(() => app.pcBaseUrl({ host: '  ' }), 'bad_url'));

/* بناء الطلبات وترويسة الرمز */
okPc('طلب ping يحمل الرمز', () => {
  const r = app.buildPcRequest({ host: '192.168.1.10', token: 'tok123' }, 'GET', '/api/ping');
  assert.strictEqual(r.url, 'http://192.168.1.10:8765/api/ping');
  assert.strictEqual(r.headers['X-Krouchi-Token'], 'tok123');
  assert.strictEqual(r.body, '');
});
okPc('طلب محادثة بجسم JSON', () => {
  const r = app.buildPcRequest({ host: 'h', token: 't' }, 'POST', '/api/chat',
    app.pcChatBody('b1', 'مرحباً'));
  assert.strictEqual(r.headers['Content-Type'], 'application/json');
  assert.deepStrictEqual(JSON.parse(r.body), { bot_id: 'b1', text: 'مرحباً' });
});
okPc('معرّف بوت نصّي رقمي يُحوَّل إلى رقم (إصلاح HTTP 400)', () => {
  assert.deepStrictEqual(app.pcChatBody('3', 'سلام'), { bot_id: 3, text: 'سلام' });
  assert.deepStrictEqual(app.pcChatBody(3, 'سلام'), { bot_id: 3, text: 'سلام' });
});
okPc('جسم قرار الموافقة', () =>
  assert.deepStrictEqual(app.pcDecisionBody('approve'), { decision: 'approve' }));
okPc('قرار غير approve يُعامَل رفضاً', () =>
  assert.deepStrictEqual(app.pcDecisionBody('whatever'), { decision: 'deny' }));

/* تحليل ردود الحاسوب */
okPc('ping سليم', () =>
  assert.deepStrictEqual(
    app.parsePing({ ok: true, app: 'Krouchi_DZ', version: '2.0' }),
    { ok: true, app: 'Krouchi_DZ', version: '2.0' }));
okPc('ping من خادم آخر → notapp', () =>
  throwsKind(() => app.parsePing({ ok: true, app: 'Other' }), 'notapp'));
okPc('بوتات الحاسوب تُطبَّع وتُصفّى', () =>
  assert.deepStrictEqual(
    app.parsePcBots({ bots: [
      { id: 7, name: 'مساعد', provider: 'openrouter', model: 'm', mode: 'ask' },
      { name: 'بلا معرّف' }, null] }),
    [{ id: '7', name: 'مساعد', provider: 'openrouter', model: 'm', mode: 'ask', avatar: '' }]));
okPc('سجلّ محادثة يُطبَّع', () =>
  assert.deepStrictEqual(
    app.parsePcHistory({ messages: [
      { role: 'user', content: 'س' }, { role: 'assistant', content: 'ج' },
      { role: 'user', content: 42 }] }),
    [{ role: 'user', content: 'س' }, { role: 'assistant', content: 'ج' }]));
okPc('موافقات معلّقة تُطبَّع', () =>
  assert.deepStrictEqual(
    app.parsePcApprovals({ pending: [
      { id: 'a1', bot_name: 'مساعد', tool: 'run_command', summary: 'تشغيل…', created: '19:00' }] }),
    [{ id: 'a1', bot_name: 'مساعد', tool: 'run_command', summary: 'تشغيل…', created: '19:00' }]));
okPc('شكل موافقات خاطئ → bad_shape', () =>
  throwsKind(() => app.parsePcApprovals({ approvals: [] }), 'bad_shape'));
okPc('ردّ محادثة الحاسوب', () =>
  assert.strictEqual(app.parsePcChatReply({ reply: 'أهلاً' }), 'أهلاً'));
okPc('ردّ محادثة بلا reply → bad_shape', () =>
  throwsKind(() => app.parsePcChatReply({ text: 'x' }), 'bad_shape'));

/* حفظ إعدادات الاتصال واسترجاعها */
okPc('حفظ ثم تحميل إعدادات الاتصال', () => {
  const saved = app.savePcConfig({ host: ' 192.168.1.20 ', port: '8765', token: ' abc ' });
  assert.deepStrictEqual(saved, { host: '192.168.1.20', port: 8765, token: 'abc', mac: '' });
  assert.deepStrictEqual(app.loadPcConfig(), saved);
});
okPc('تطبيع الإعدادات: منفذ نصي وفراغات', () =>
  assert.deepStrictEqual(
    app.normalizePcConfig({ host: ' h ', port: '9001', token: ' t ' }),
    { host: 'h', port: 9001, token: 't', mac: '' }));

/* اختبارات غير متزامنة: pcRequest بنقل وهمي + المُستطلِع بمؤقّتات وهمية */
let passedAsync = 0;
async function okAsync(name, fn) {
  try { await fn(); passedAsync++; console.log('✔ [حاسوب] ' + name); }
  catch (e) { console.error('✘ [حاسوب] ' + name + ': ' + e.message); process.exitCode = 1; }
}
async function rejectsKind(promise, kind) {
  try { await promise; } catch (e) { assert.strictEqual(e.kind, kind, 'kind=' + e.kind); return; }
  throw new Error('لم يُرفَض الوعد');
}
const flush = () => new Promise((r) => setImmediate(r));
function mockTransport(res, capture) {
  return function (method, url, headers, body, timeoutMs) {
    if (capture) Object.assign(capture, { method, url, headers, body, timeoutMs });
    return Promise.resolve(res);
  };
}

(async () => {
  const cfg = { host: '192.168.1.10', port: 8765, token: 'tok123' };

  await okAsync('pcRequest ناجح: رابط ورمز ومهلة', async () => {
    const cap = {};
    const data = await app.pcRequest(cfg, 'GET', '/api/ping', null, 5000,
      mockTransport({ status: 200, text: '{"ok":true,"app":"Krouchi_DZ","version":"2.0"}', error: '' }, cap));
    assert.strictEqual(cap.url, 'http://192.168.1.10:8765/api/ping');
    assert.strictEqual(cap.headers['X-Krouchi-Token'], 'tok123');
    assert.strictEqual(cap.timeoutMs, 5000);
    assert.strictEqual(app.parsePing(data).version, '2.0');
  });
  await okAsync('pcRequest 401 → auth (رمز مرفوض)', () =>
    rejectsKind(app.pcRequest(cfg, 'GET', '/api/bots', null, null,
      mockTransport({ status: 401, text: '', error: '' })), 'auth'));
  await okAsync('pcRequest بلا شبكة → unreachable', () =>
    rejectsKind(app.pcRequest(cfg, 'GET', '/api/bots', null, null,
      mockTransport({ status: 0, text: '', error: 'ConnectException' })), 'unreachable'));
  await okAsync('pcRequest ردّ غير JSON → not_json', () =>
    rejectsKind(app.pcRequest(cfg, 'GET', '/api/bots', null, null,
      mockTransport({ status: 200, text: '<html>', error: '' })), 'not_json'));
  await okAsync('pcRequest قرار موافقة يُبنى صحيحاً', async () => {
    const cap = {};
    await app.pcRequest(cfg, 'POST', '/api/approvals/a1',
      app.pcDecisionBody('deny'), null,
      mockTransport({ status: 200, text: '{"ok":true}', error: '' }, cap));
    assert.strictEqual(cap.url, 'http://192.168.1.10:8765/api/approvals/a1');
    assert.deepStrictEqual(JSON.parse(cap.body), { decision: 'deny' });
  });

  await okAsync('المُستطلِع: بداية فورية وجولات وإيقاف', async () => {
    const timers = new Map(); let seq = 0; let calls = 0; const seen = [];
    const poller = app.createPoller({
      intervalMs: 1000,
      task: () => Promise.resolve(++calls),
      onResult: (r) => seen.push(r),
      setIntervalFn: (fn) => { const id = ++seq; timers.set(id, fn); return id; },
      clearIntervalFn: (id) => { timers.delete(id); }
    });
    poller.start();
    await flush();
    assert.strictEqual(calls, 1, 'جولة فورية عند البدء');
    [...timers.values()].forEach((fn) => fn());
    await flush();
    assert.strictEqual(calls, 2, 'جولة عند المؤقّت');
    poller.stop();
    assert.strictEqual(timers.size, 0, 'المؤقّت أُلغي');
    [...timers.values()].forEach((fn) => fn());
    await flush();
    assert.strictEqual(calls, 2, 'لا جولات بعد الإيقاف');
    assert.deepStrictEqual(seen, [1, 2]);
  });

  await okAsync('المُستطلِع: لا تزامن بين جولتين', async () => {
    let calls = 0; let release = null;
    const poller = app.createPoller({
      intervalMs: 1000,
      task: () => { calls++; return new Promise((r) => { release = r; }); },
      setIntervalFn: () => 1,
      clearIntervalFn: () => {}
    });
    poller.start();
    poller.tick();
    poller.tick();
    assert.strictEqual(calls, 1, 'الجولة المعلّقة تمنع جولات موازية');
    release('x');
    await flush();
    poller.tick();
    assert.strictEqual(calls, 2, 'جولة جديدة بعد انتهاء السابقة');
    poller.stop();
  });

  await okAsync('pcRequest 403 بجسم denied → kind denied (رفض موافقة)', () =>
    rejectsKind(app.pcRequest(cfg, 'POST', '/api/run', app.runBody('dir'), null,
      mockTransport({ status: 403, text: '{"error":"denied"}', error: '' })), 'denied'));
  await okAsync('pcRequest 403 بلا denied → auth (رمز مرفوض)', () =>
    rejectsKind(app.pcRequest(cfg, 'GET', '/api/bots', null, null,
      mockTransport({ status: 403, text: '', error: '' })), 'auth'));
  await okAsync('إنشاء مهمة: جسم الطلب وتحليل الردّ', async () => {
    const cap = {};
    const data = await app.pcRequest(cfg, 'POST', '/api/tasks',
      app.taskBody('3', 'مهمة', 'نفّذ كذا'), null,
      mockTransport({ status: 200,
        text: JSON.stringify({ task: { id: 9, bot_id: 3, title: 'مهمة',
          status: 'queued', created_at: 't' } }), error: '' }, cap));
    assert.strictEqual(cap.url, 'http://192.168.1.10:8765/api/tasks');
    assert.deepStrictEqual(JSON.parse(cap.body),
      { bot_id: 3, title: 'مهمة', prompt: 'نفّذ كذا' });
    const created = app.parseTaskDetail(data);
    assert.strictEqual(created.id, '9');
    assert.strictEqual(created.status, 'queued');
    assert.deepStrictEqual(created.log, []);
  });

  console.log('\n' + (passedPc + passedAsync) + ' اختباراً للوضع المرافق ناجحاً');
})();

/* ================= تعدّد اللغات (i18n): العربية والإنجليزية فقط ================= */

let passedI18n = 0;
function okI(name, fn) {
  try { fn(); passedI18n++; console.log('✔ [لغات] ' + name); }
  catch (e) { console.error('✘ [لغات] ' + name + ': ' + e.message); process.exitCode = 1; }
}

okI('اللغات المدعومة: العربية والإنجليزية فقط', () =>
  assert.deepStrictEqual(app.SUPPORTED_LANGS, ['ar', 'en']));

okI('تكافؤ مفاتيح ar/en (نفس المجموعة تماماً)', () => {
  const a = Object.keys(app.STRINGS.ar).sort();
  const e = Object.keys(app.STRINGS.en).sort();
  assert.deepStrictEqual(e, a);
  assert.ok(a.length >= 90, 'عدد المفاتيح: ' + a.length);
});

okI('لا قيم فارغة أو غير نصية في أي لغة', () => {
  for (const lang of app.SUPPORTED_LANGS) {
    for (const k of Object.keys(app.STRINGS[lang])) {
      assert.strictEqual(typeof app.STRINGS[lang][k], 'string', lang + ':' + k);
      assert.ok(app.STRINGS[lang][k].trim().length > 0, lang + ':' + k + ' فارغ');
    }
  }
});

okI('t() يعيد الإنجليزية بعد التبديل إليها', () => {
  app.setLang('en');
  assert.strictEqual(app.getLang(), 'en');
  assert.strictEqual(app.t('tab_bots'), app.STRINGS.en.tab_bots);
  assert.strictEqual(app.t('btn_send'), 'Send');
  assert.strictEqual(app.t('btn_approve'), '✅ Approve');
});

okI('t() يحلّ المتغيرات {name}/{count}', () => {
  app.setLang('en');
  assert.strictEqual(
    app.t('api_success', { name: 'x', count: 3 }),
    'Success: x — 3 models available');
  app.setLang('ar');
  assert.strictEqual(
    app.t('approvals_waiting', { count: 2 }), '2 بانتظار قرارك');
});

okI('احتياط t(): لغة غير مدعومة → العربية، ومفتاح مجهول → المفتاح نفسه', () => {
  assert.strictEqual(app.translate('fr', 'tab_bots'), app.STRINGS.ar.tab_bots);
  assert.strictEqual(app.t('no_such_key_xyz'), 'no_such_key_xyz');
});

okI('حفظ اختيار اللغة واسترجاعه (ذهاب وإياب)', () => {
  app.setLang('en');
  assert.strictEqual(__lsStore['krouchi.lang.v1'], 'en');
  assert.strictEqual(app.loadLang(), 'en');
  app.setLang('ar');
  assert.strictEqual(__lsStore['krouchi.lang.v1'], 'ar');
  assert.strictEqual(app.loadLang(), 'ar');
});

okI('قيمة لغة فاسدة في التخزين → الافتراضي العربية', () => {
  __lsStore['krouchi.lang.v1'] = 'fr';
  assert.strictEqual(app.loadLang(), 'ar');
  delete __lsStore['krouchi.lang.v1'];
  assert.strictEqual(app.loadLang(), 'ar');
});

/* عرض عناوين التبويبات عبر localizeDocument على مستند وهمي */
function fakeTextEl(attrs) {
  return {
    _attrs: Object.assign({}, attrs),
    textContent: '',
    innerHTML: '',
    getAttribute: function (k) { return this._attrs[k] || null; },
    setAttribute: function (k, v) { this._attrs[k] = v; }
  };
}

okI('localizeDocument: تبويبات إنجليزية + اتجاه LTR + تلميح', () => {
  const tabKeys = ['tab_api', 'tab_bots', 'tab_chat', 'tab_pc', 'tab_about'];
  const els = tabKeys.map((k) => fakeTextEl({ 'data-i18n': k }));
  const phEl = fakeTextEl({ 'data-i18n-ph': 'ph_message' });
  const fakeDoc = {
    documentElement: {
      _attrs: {},
      setAttribute: function (k, v) { this._attrs[k] = v; }
    },
    querySelectorAll: function (sel) {
      if (sel === '[data-i18n]') return els;
      if (sel === '[data-i18n-ph]') return [phEl];
      return [];
    }
  };
  app.localizeDocument(fakeDoc, 'en');
  assert.deepStrictEqual(
    els.map((e) => e.textContent),
    tabKeys.map((k) => app.STRINGS.en[k]));
  assert.strictEqual(fakeDoc.documentElement._attrs.lang, 'en');
  assert.strictEqual(fakeDoc.documentElement._attrs.dir, 'ltr');
  assert.strictEqual(phEl._attrs.placeholder, app.STRINGS.en.ph_message);
  app.localizeDocument(fakeDoc, 'ar');
  assert.deepStrictEqual(
    els.map((e) => e.textContent),
    tabKeys.map((k) => app.STRINGS.ar[k]));
  assert.strictEqual(fakeDoc.documentElement._attrs.dir, 'rtl');
});

app.setLang('ar');
console.log('\n' + passedI18n + ' اختباراً للغات ناجحاً');
/* ================= المهام والتحكّم الكلّي (v3.2): دوال نقية ================= */

let passedCtl = 0;
function okCtl(name, fn) {
  try { fn(); passedCtl++; console.log('✔ [تحكّم] ' + name); }
  catch (e) { console.error('✘ [تحكّم] ' + name + ': ' + e.message); process.exitCode = 1; }
}

app.setLang('ar');

/* تحويل المعرّفات */
okCtl('coerceNumericId: نصّ رقمي → رقم، وغيره يبقى', () => {
  assert.strictEqual(app.coerceNumericId('7'), 7);
  assert.strictEqual(app.coerceNumericId(7), 7);
  assert.strictEqual(app.coerceNumericId('-3'), -3);
  assert.strictEqual(app.coerceNumericId('b1'), 'b1');
  assert.strictEqual(app.coerceNumericId('3.5'), '3.5');
});

/* المهام: الأجسام والتحليل والتسميات */
okCtl('taskBody: معرّف نصّي رقمي يُحوَّل إلى رقم', () => {
  assert.deepStrictEqual(app.taskBody('5', 'عنوان', 'نصّ'),
    { bot_id: 5, title: 'عنوان', prompt: 'نصّ' });
  assert.deepStrictEqual(app.taskBody(5, 't', 'p'),
    { bot_id: 5, title: 't', prompt: 'p' });
  assert.deepStrictEqual(app.taskBody('b1', 't', 'p'),
    { bot_id: 'b1', title: 't', prompt: 'p' });
});
okCtl('parseTasks: تطبيع وتصفية', () =>
  assert.deepStrictEqual(
    app.parseTasks({ tasks: [
      { id: 3, bot_id: 2, bot_name: 'مساعد', title: 'مهمة', status: 'running',
        created_at: 'c', started_at: 's', finished_at: '' },
      { title: 'بلا معرّف' }, null, { id: 'x', title: 'ثانية' }] }),
    [{ id: '3', bot_id: 2, bot_name: 'مساعد', title: 'مهمة', status: 'running',
       created_at: 'c', started_at: 's', finished_at: '' },
     { id: 'x', bot_id: '', bot_name: '', title: 'ثانية', status: '',
       created_at: '', started_at: '', finished_at: '' }]));
okCtl('parseTasks: شكل خاطئ → bad_shape', () =>
  throwsKind(() => app.parseTasks({ tasks: {} }), 'bad_shape'));
okCtl('parseTaskDetail: حقل كامل مع سجلّ مختلط', () =>
  assert.deepStrictEqual(
    app.parseTaskDetail({ task: {
      id: 9, bot_id: 3, bot_name: 'بوت', title: 'م', status: 'done',
      created_at: 'c', prompt: 'نفّذ', result: 'تمّ', error: null,
      log: [{ ts: '1', kind: 'tool', text: 'شغّل' }, 'سطر نصّي', 42] } }),
    { id: '9', bot_id: 3, bot_name: 'بوت', title: 'م', status: 'done',
      created_at: 'c', started_at: '', finished_at: '',
      prompt: 'نفّذ', result: 'تمّ', error: '',
      log: [{ ts: '1', kind: 'tool', text: 'شغّل' },
            { ts: '', kind: '', text: 'سطر نصّي' }] }));
okCtl('parseTaskDetail: بلا task → bad_shape', () =>
  throwsKind(() => app.parseTaskDetail({}), 'bad_shape'));
okCtl('تسميات الحالات الستّ في اللغتين + المجهولة', () => {
  assert.deepStrictEqual(app.TASK_STATUSES,
    ['queued', 'running', 'waiting_approval', 'done', 'failed', 'cancelled']);
  app.setLang('ar');
  for (const s of app.TASK_STATUSES) {
    assert.strictEqual(app.taskStatusKey(s), 'task_status_' + s);
    assert.strictEqual(app.taskStatusLabel(s), app.STRINGS.ar['task_status_' + s]);
  }
  app.setLang('en');
  for (const s of app.TASK_STATUSES) {
    assert.strictEqual(app.taskStatusLabel(s), app.STRINGS.en['task_status_' + s]);
  }
  assert.strictEqual(app.taskStatusKey('zzz'), 'task_status_unknown');
  assert.strictEqual(app.taskStatusLabel('zzz'), app.STRINGS.en.task_status_unknown);
  app.setLang('ar');
  assert.strictEqual(app.taskStatusLabel('zzz'), app.STRINGS.ar.task_status_unknown);
});

/* الحالة والتنسيقات */
okCtl('parseStatus: حقل كامل', () =>
  assert.deepStrictEqual(
    app.parseStatus({ app: 'Krouchi_DZ', version: '3.2.0', os: 'Windows 11',
      platform: 'win32', hostname: 'PC', home: 'C:\\Users\\u', uptime_s: 3661,
      disk: { total_gb: 500, free_gb: 120 }, ram_mb: 8192 }),
    { app: 'Krouchi_DZ', version: '3.2.0', os: 'Windows 11', platform: 'win32',
      hostname: 'PC', home: 'C:\\Users\\u', uptime_s: 3661,
      disk: { total_gb: 500, free_gb: 120 }, ram_mb: 8192 }));
okCtl('parseStatus: قرص وذاكرة غائبان → null', () => {
  const st = app.parseStatus({ hostname: 'H' });
  assert.strictEqual(st.disk, null);
  assert.strictEqual(st.ram_mb, null);
  assert.strictEqual(st.uptime_s, 0);
});
okCtl('parseStatus: null → bad_shape', () =>
  throwsKind(() => app.parseStatus(null), 'bad_shape'));
okCtl('formatUptime', () => {
  assert.strictEqual(app.formatUptime(0), '0:00:00');
  assert.strictEqual(app.formatUptime(59), '0:00:59');
  assert.strictEqual(app.formatUptime(60), '0:01:00');
  assert.strictEqual(app.formatUptime(3661), '1:01:01');
  assert.strictEqual(app.formatUptime(90061), '1d 1:01:01');
  assert.strictEqual(app.formatUptime(-5), '0:00:00');
  assert.strictEqual(app.formatUptime('x'), '0:00:00');
});
okCtl('formatSize بالعربية والإنجليزية', () => {
  app.setLang('ar');
  assert.strictEqual(app.formatSize(0), '0 بايت');
  assert.strictEqual(app.formatSize(500), '500 بايت');
  assert.strictEqual(app.formatSize(2048), '2 KB');
  assert.strictEqual(app.formatSize(1536), '1.5 KB');
  assert.strictEqual(app.formatSize(3145728), '3 MB');
  assert.strictEqual(app.formatSize(null), '');
  assert.strictEqual(app.formatSize(-1), '');
  app.setLang('en');
  assert.strictEqual(app.formatSize(0), '0 B');
  app.setLang('ar');
});

/* الملفّات */
okCtl('parseFiles: تطبيع الأنواع والأحجام', () =>
  assert.deepStrictEqual(
    app.parseFiles({ path: '/home/u', parent: '/home', entries: [
      { name: 'docs', kind: 'dir', size: null },
      { name: 'a.txt', kind: 'file', size: 12 },
      { name: 'b.bin', kind: 'other', size: '9' },
      { name: '' }, { kind: 'file' }, null] }),
    { path: '/home/u', parent: '/home', entries: [
      { name: 'docs', kind: 'dir', size: null },
      { name: 'a.txt', kind: 'file', size: 12 },
      { name: 'b.bin', kind: 'file', size: null }] }));
okCtl('parseFiles: أب غائب → null، وشكل خاطئ → bad_shape', () => {
  assert.strictEqual(app.parseFiles({ path: '/', parent: null, entries: [] }).parent, null);
  throwsKind(() => app.parseFiles({ entries: {} }), 'bad_shape');
});
okCtl('joinRemotePath: فواصل المنصّتين والجذور', () => {
  assert.strictEqual(app.joinRemotePath('/home/u', 'a.txt'), '/home/u/a.txt');
  assert.strictEqual(app.joinRemotePath('/home/u/', 'a.txt'), '/home/u/a.txt');
  assert.strictEqual(app.joinRemotePath('/', 'a.txt'), '/a.txt');
  assert.strictEqual(app.joinRemotePath('C:\\Users\\u', 'a.txt'), 'C:\\Users\\u\\a.txt');
  assert.strictEqual(app.joinRemotePath('C:\\', 'a.txt'), 'C:\\a.txt');
  assert.strictEqual(app.joinRemotePath('', 'a.txt'), 'a.txt');
});
okCtl('parseFileDownload: شكل سليم وخاطئ', () => {
  assert.deepStrictEqual(
    app.parseFileDownload({ name: 'a.txt', size: 3, content_b64: 'QUJD' }),
    { name: 'a.txt', size: 3, content_b64: 'QUJD' });
  throwsKind(() => app.parseFileDownload({ name: 'a' }), 'bad_shape');
  throwsKind(() => app.parseFileDownload({ content_b64: 5 }), 'bad_shape');
});

/* التشغيل والفتح والطاقة واللقطة */
okCtl('runBody + parseRunResult', () => {
  assert.deepStrictEqual(app.runBody('dir'), { command: 'dir' });
  assert.deepStrictEqual(app.runBody(null), { command: '' });
  assert.deepStrictEqual(
    app.parseRunResult({ exit: 0, stdout: 'a', stderr: '', timed_out: false }),
    { exit: 0, stdout: 'a', stderr: '', timed_out: false });
  assert.deepStrictEqual(app.parseRunResult({}),
    { exit: null, stdout: '', stderr: '', timed_out: false });
  throwsKind(() => app.parseRunResult(null), 'bad_shape');
});
okCtl('openBody', () =>
  assert.deepStrictEqual(app.openBody('notepad'), { target: 'notepad' }));
okCtl('powerBody: الإجراءات الخمسة + افتراضي آمن', () => {
  assert.deepStrictEqual(app.POWER_ACTIONS,
    ['shutdown', 'restart', 'lock', 'sleep', 'logoff']);
  for (const a of app.POWER_ACTIONS) {
    assert.deepStrictEqual(app.powerBody(a), { action: a });
  }
  assert.deepStrictEqual(app.powerBody('bogus'), { action: 'shutdown' });
});
okCtl('parsePower', () => {
  assert.deepStrictEqual(app.parsePower({ ok: true, scheduled_in_s: 30 }),
    { ok: true, scheduled_in_s: 30 });
  assert.deepStrictEqual(app.parsePower({ ok: true }),
    { ok: true, scheduled_in_s: null });
});
okCtl('parseScreenshot + screenshotDataUri', () => {
  assert.deepStrictEqual(
    app.parseScreenshot({ image_b64: 'QUJD', format: 'png' }),
    { image_b64: 'QUJD', format: 'png' });
  assert.strictEqual(
    app.screenshotDataUri({ image_b64: 'QUJD', format: 'png' }),
    'data:image/png;base64,QUJD');
  assert.strictEqual(
    app.screenshotDataUri({ image_b64: 'QUJD', format: 'JPG ' }),
    'data:image/jpg;base64,QUJD');
  assert.strictEqual(
    app.screenshotDataUri({ image_b64: 'QUJD' }),
    'data:image/png;base64,QUJD');
  throwsKind(() => app.parseScreenshot({ image_b64: '' }), 'bad_shape');
});

/* الطباعة والرفع والحافظة */
okCtl('printBody: بلا طابعة تُحذف، وبها تُقصّ', () => {
  const b1 = app.printBody('/a/b.txt', '');
  assert.deepStrictEqual(b1, { path: '/a/b.txt' });
  assert.ok(!('printer' in b1), 'لا مفتاح printer عند الفراغ');
  assert.deepStrictEqual(app.printBody('/a/b.txt', ' HP '),
    { path: '/a/b.txt', printer: 'HP' });
  assert.deepStrictEqual(app.printBody('/a/b.txt', null), { path: '/a/b.txt' });
});
okCtl('parsePrinters: تطبيع وتصفية', () => {
  assert.deepStrictEqual(
    app.parsePrinters({ printers: [
      { name: 'HP', is_default: true }, { name: 'PDF', is_default: 1 },
      { name: '' }, null] }),
    [{ name: 'HP', is_default: true }, { name: 'PDF', is_default: false }]);
  throwsKind(() => app.parsePrinters({ printers: {} }), 'bad_shape');
});
okCtl('uploadBody: فصل Base64 عن بادئة data:', () => {
  assert.deepStrictEqual(
    app.uploadBody('a.txt', 'data:text/plain;base64,QUJD'),
    { path: 'a.txt', content_b64: 'QUJD' });
  assert.deepStrictEqual(
    app.uploadBody('a.txt', 'QUJD'), { path: 'a.txt', content_b64: 'QUJD' });
  assert.deepStrictEqual(
    app.uploadBody('a.txt', 'data:image/png;base64,QU JD\n'),
    { path: 'a.txt', content_b64: 'QUJD' });
  assert.deepStrictEqual(
    app.uploadBody(null, null), { path: '', content_b64: '' });
});
okCtl('clipboardBody + parseClipboard', () => {
  assert.deepStrictEqual(app.clipboardBody('نصّ'), { text: 'نصّ' });
  assert.deepStrictEqual(app.clipboardBody(null), { text: '' });
  assert.strictEqual(app.parseClipboard({ text: 'x' }), 'x');
  throwsKind(() => app.parseClipboard({}), 'bad_shape');
  throwsKind(() => app.parseClipboard({ text: 5 }), 'bad_shape');
});

/* الصوت والنوافذ والعمليات */
okCtl('volumeBody', () => {
  assert.deepStrictEqual(app.volumeBody('up'), { action: 'up' });
  assert.deepStrictEqual(app.volumeBody('down'), { action: 'down' });
  assert.deepStrictEqual(app.volumeBody('mute'), { action: 'mute' });
  assert.deepStrictEqual(app.volumeBody('bogus'), { action: 'mute' });
});
okCtl('parseWindows + windowBody', () => {
  assert.deepStrictEqual(
    app.parseWindows({ windows: [{ id: 123, title: 'محرّر' }, { id: 'w2' }, { title: 'x' }] }),
    [{ id: 123, title: 'محرّر' }, { id: 'w2', title: '' }]);
  throwsKind(() => app.parseWindows({ windows: {} }), 'bad_shape');
  assert.deepStrictEqual(app.windowBody('42', 'close'), { id: 42, action: 'close' });
  assert.deepStrictEqual(app.windowBody(7, 'bogus'), { id: 7, action: 'focus' });
  assert.deepStrictEqual(app.windowBody('hwnd', 'focus'), { id: 'hwnd', action: 'focus' });
});
okCtl('parseProcesses + killBody', () => {
  assert.deepStrictEqual(
    app.parseProcesses({ processes: [
      { pid: 10, name: 'a.exe', mem_mb: 120 }, { pid: '12', name: 'b', mem_mb: 'x' },
      { pid: 'x', name: 'c' }, null] }),
    [{ pid: 10, name: 'a.exe', mem_mb: 120 }, { pid: 12, name: 'b', mem_mb: null }]);
  throwsKind(() => app.parseProcesses({ processes: {} }), 'bad_shape');
  assert.deepStrictEqual(app.killBody('42'), { pid: 42 });
  assert.deepStrictEqual(app.killBody(42), { pid: 42 });
});
okCtl('طلب إنشاء مهمة يُبنى عبر buildPcRequest', () => {
  const r = app.buildPcRequest({ host: 'h', token: 't' }, 'POST', '/api/tasks',
    app.taskBody('3', 'م', 'ن'));
  assert.strictEqual(r.url, 'http://h:8765/api/tasks');
  assert.deepStrictEqual(JSON.parse(r.body), { bot_id: 3, title: 'م', prompt: 'ن' });
});

app.setLang('ar');
console.log('\n' + passedCtl + ' اختباراً للمهام والتحكّم ناجحاً');

/* ================= إيقاظ الحاسوب (Wake-on-LAN) ================= */
const fs = require('fs');
const path = require('path');
let passedWol = 0;
function okWol(name, fn) {
  try { fn(); passedWol++; console.log('✔ [إيقاظ] ' + name); }
  catch (e) { console.error('✘ [إيقاظ] ' + name + ': ' + e.message); process.exitCode = 1; }
}

okWol('normalizeMac: الصيغ المقبولة تُطبَّع إلى القانونية', () => {
  assert.strictEqual(app.normalizeMac('AA:BB:CC:DD:EE:FF'), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac('aa-bb-cc-dd-ee-ff'), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac('aabbccddeeff'), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac(' Aa:Bb:Cc:Dd:Ee:Ff '), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac('01:23:45:67:89:ab'), '01:23:45:67:89:AB');
});
okWol('normalizeMac: الصيغ المرفوضة تعيد null', () => {
  assert.strictEqual(app.normalizeMac('AA:BB:CC:DD:EE'), null);
  assert.strictEqual(app.normalizeMac('AA:BB:CC:DD:EE:FF:00'), null);
  assert.strictEqual(app.normalizeMac('GG:BB:CC:DD:EE:FF'), null);
  assert.strictEqual(app.normalizeMac('AABBCCDDEEFFA'), null);
  assert.strictEqual(app.normalizeMac(''), null);
  assert.strictEqual(app.normalizeMac(null), null);
  assert.strictEqual(app.normalizeMac(undefined), null);
});
okWol('إعدادات الاتصال: حفظ MAC بصيغته القانونية واسترجاعه', () => {
  const saved = app.savePcConfig({ host: 'h', port: 8765, token: 't', mac: 'aa-bb-cc-dd-ee-ff' });
  assert.strictEqual(saved.mac, 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.loadPcConfig().mac, 'AA:BB:CC:DD:EE:FF');
});
okWol('إعدادات الاتصال: كائن قديم بلا mac لا ينكسر', () => {
  __lsStore['krouchi.pc.v1'] = JSON.stringify({ host: 'old', port: 8765, token: 'x' });
  const old = app.loadPcConfig();
  assert.strictEqual(old.host, 'old');
  assert.strictEqual(old.mac, '');
  assert.strictEqual(app.normalizePcConfig({ host: 'h' }).mac, '');
  assert.strictEqual(app.normalizePcConfig({ mac: 'bogus' }).mac, '');
  assert.strictEqual(app.defaultPcConfig().mac, '');
});
okWol('markup: حقل MAC وزر الإيقاظ موجودان في الواجهة', () => {
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  assert.ok(html.indexOf('id="pcMac"') >= 0, 'missing #pcMac');
  assert.ok(html.indexOf('id="pcWakeBtn"') >= 0, 'missing #pcWakeBtn');
});
console.log('\n' + passedWol + ' اختباراً للإيقاظ ناجحاً');

/* ================= الشاشة الحية (v3.3): دوال نقية ================= */
let passedScr = 0;
function okScr(name, fn) {
  try { fn(); passedScr++; console.log('✔ [شاشة] ' + name); }
  catch (e) { console.error('✘ [شاشة] ' + name + ': ' + e.message); process.exitCode = 1; }
}

okScr('screenStreamUrl: الشكل الكامل بخيارات صريحة', () => {
  assert.strictEqual(
    app.screenStreamUrl({ host: '192.168.1.10', token: 'tok123' }, { w: 1280, q: 60, fps: 10 }),
    'http://192.168.1.10:8765/api/screen/stream?token=tok123&w=1280&q=60&fps=10');
});
okScr('screenStreamUrl: ترميز الرمز وخيارات ومنفذ مخصصة وافتراضيات', () => {
  assert.strictEqual(
    app.screenStreamUrl({ host: 'pc.local', port: 9000, token: 'a b&c=d' }, { w: 960, q: 40, fps: 5 }),
    'http://pc.local:9000/api/screen/stream?token=a%20b%26c%3Dd&w=960&q=40&fps=5');
  assert.strictEqual(
    app.screenStreamUrl({ host: '192.168.1.10', token: 't' }),
    'http://192.168.1.10:8765/api/screen/stream?token=t&w=1280&q=60&fps=10');
});
okScr('screenFramePath: مسار الإطار المفرد والافتراضيات (v3.3.2)', () => {
  assert.strictEqual(
    app.screenFramePath({ w: 1280, q: 60 }),
    '/api/screen/frame?w=1280&q=60');
  assert.strictEqual(app.screenFramePath(), '/api/screen/frame?w=1280&q=60');
  assert.strictEqual(
    app.screenFramePath({ w: 640, q: 45 }),
    '/api/screen/frame?w=640&q=45');
});
okScr('normPoint: الزوايا والمركز والربع', () => {
  const rect = { left: 100, top: 50, width: 400, height: 200 };
  assert.deepStrictEqual(app.normPoint(100, 50, rect), { x: 0, y: 0 });
  assert.deepStrictEqual(app.normPoint(500, 250, rect), { x: 1, y: 1 });
  assert.deepStrictEqual(app.normPoint(300, 150, rect), { x: 0.5, y: 0.5 });
  assert.deepStrictEqual(app.normPoint(200, 100, rect), { x: 0.25, y: 0.25 });
});
okScr('normPoint: الخروج عن الصورة يُقصّ، ومستطيل فاسد → الصفر', () => {
  const rect = { left: 0, top: 0, width: 100, height: 100 };
  assert.deepStrictEqual(app.normPoint(-20, 130, rect), { x: 0, y: 1 });
  assert.deepStrictEqual(app.normPoint(50, 50, { left: 0, top: 0, width: 0, height: 100 }), { x: 0, y: 0 });
  assert.deepStrictEqual(app.normPoint(50, 50, null), { x: 0, y: 0 });
});
okScr('inputMouseBody: الأنواع والأزرار والقصّ', () => {
  assert.deepStrictEqual(app.inputMouseBody('mouse_down', { x: 0.5, y: 0.25 }),
    { type: 'mouse_down', x: 0.5, y: 0.25, button: 'left' });
  assert.deepStrictEqual(app.inputMouseBody('mouse_up', { x: 0, y: 1 }, 'right'),
    { type: 'mouse_up', x: 0, y: 1, button: 'right' });
  assert.deepStrictEqual(app.inputMouseBody('mouse_move', { x: 1.4, y: -0.2 }),
    { type: 'mouse_move', x: 1, y: 0, button: 'left' });
  assert.deepStrictEqual(app.inputMouseBody('bogus', { x: 0.5, y: 0.5 }, 'weird'),
    { type: 'mouse_move', x: 0.5, y: 0.5, button: 'left' });
});
okScr('inputWheelBody: الاتجاهان عند مركز الصورة', () => {
  assert.deepStrictEqual(app.inputWheelBody({ x: 0.5, y: 0.5 }, 1),
    { type: 'wheel', x: 0.5, y: 0.5, delta: 1 });
  assert.deepStrictEqual(app.inputWheelBody({ x: 0.5, y: 0.5 }, -1),
    { type: 'wheel', x: 0.5, y: 0.5, delta: -1 });
});
okScr('inputKeyBody + inputTextBody', () => {
  assert.deepStrictEqual(app.inputKeyBody('ctrl+c'), { type: 'key', key: 'ctrl+c' });
  assert.deepStrictEqual(app.inputKeyBody(null), { type: 'key', key: '' });
  assert.deepStrictEqual(app.inputTextBody('مرحباً'), { type: 'text', text: 'مرحباً' });
  assert.deepStrictEqual(app.inputTextBody(null), { type: 'text', text: '' });
});
okScr('markup: قسم الشاشة وعناصره ومفاتيحه في الواجهة', () => {
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  const ids = ['pc-screen-wrap', 'screen-start', 'screen-stop', 'screen-drag',
    'screen-status', 'pcScreenImg', 'screen-wheel-up', 'screen-wheel-down',
    'screen-text', 'screen-send-text'];
  for (const id of ids) {
    assert.ok(html.indexOf('id="' + id + '"') >= 0, 'missing #' + id);
  }
  const keys = ['enter', 'esc', 'tab', 'backspace', 'delete', 'up', 'down',
    'left', 'right', 'ctrl+c', 'ctrl+v', 'ctrl+z', 'alt+tab', 'win'];
  for (const k of keys) {
    assert.ok(html.indexOf('data-screen-key="' + k + '"') >= 0, 'missing key ' + k);
  }
});
console.log('\n' + passedScr + ' اختباراً للشاشة ناجحاً');

/* ================= v3.4: سجلّ الحواسيب المتعدّدة ================= */
let passedReg = 0;
function okReg(name, fn) {
  try { fn(); passedReg++; console.log('✔ [سجلّ] ' + name); }
  catch (e) { console.error('✘ [سجلّ] ' + name + ': ' + e.message); process.exitCode = 1; }
}
function clearPcKeys() {
  delete __lsStore['krouchi.pcs.v1'];
  delete __lsStore['krouchi.pcs.active.v1'];
  delete __lsStore['krouchi.pc.v1'];
}

okReg('هجرة الإرث: إدخال وحيد نشط بحقول مُسندة', () => {
  clearPcKeys();
  __lsStore['krouchi.pc.v1'] = JSON.stringify(
    { host: '192.168.1.50', port: 9000, token: 'tok-legacy', mac: 'aa-bb-cc-dd-ee-ff' });
  const reg = app.loadPcRegistry();
  assert.strictEqual(reg.length, 1);
  assert.strictEqual(reg[0].host, '192.168.1.50');
  assert.strictEqual(reg[0].port, 9000);
  assert.strictEqual(reg[0].token, 'tok-legacy');
  assert.strictEqual(reg[0].mac, 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(reg[0].name, '192.168.1.50');
  assert.strictEqual(app.getActivePcId(), reg[0].id);
  assert.deepStrictEqual(app.loadPcConfig(),
    { host: '192.168.1.50', port: 9000, token: 'tok-legacy', mac: 'AA:BB:CC:DD:EE:FF' });
});

okReg('اسم الإرث يُحفظ عند الهجرة إن وُجد', () => {
  clearPcKeys();
  __lsStore['krouchi.pc.v1'] = JSON.stringify(
    { name: 'حاسوب البيت', host: 'h1', port: 8765, token: 't' });
  const reg = app.loadPcRegistry();
  assert.strictEqual(reg[0].name, 'حاسوب البيت');
});

okReg('إضافة وتبديل وحذف إدخالات السجلّ', () => {
  clearPcKeys();
  const a = app.addPcEntry({ name: 'Alpha', host: '10.0.0.1', token: 'ta' });
  const b = app.addPcEntry({ name: 'Beta', host: '10.0.0.2', token: 'tb' });
  assert.strictEqual(app.loadPcRegistry().length, 2);
  assert.strictEqual(app.getActivePcEntry().id, b.id, 'الأخير المضاف نشط');
  const sw = app.setActivePcEntry(a.id);
  assert.strictEqual(sw.name, 'Alpha');
  assert.strictEqual(app.getActivePcId(), a.id);
  assert.strictEqual(app.loadPcConfig().host, '10.0.0.1');
  const after = app.removePcEntry(a.id);
  assert.strictEqual(after.id, b.id, 'الحذف يفعّل التالي');
  assert.strictEqual(app.loadPcRegistry().length, 1);
  const none = app.removePcEntry(b.id);
  assert.strictEqual(none, null);
  assert.deepStrictEqual(app.loadPcRegistry(), []);
});

okReg('resolvePcEntry: افتراضي نشط، وبالاسم، ومجهول يسرد المتاح', () => {
  const reg = [
    { id: 'p1', name: 'Home PC', host: 'h1', port: 8765, token: 't', mac: '' },
    { id: 'p2', name: 'Office', host: 'h2', port: 8765, token: 't', mac: '' }];
  assert.strictEqual(app.resolvePcEntry('', reg, 'p2').entry.name, 'Office');
  assert.strictEqual(app.resolvePcEntry('home pc', reg, 'p2').entry.id, 'p1');
  const miss = app.resolvePcEntry('Nope', reg, 'p1');
  assert.strictEqual(miss.entry, null);
  assert.ok(miss.error.indexOf('computer not found: Nope') === 0);
  assert.ok(miss.error.indexOf('Home PC') >= 0 && miss.error.indexOf('Office') >= 0);
});

okReg('providerKind: gemini بالحقل أو العنوان أو الاسم، وغيره openai', () => {
  assert.strictEqual(app.providerKind({ kind: 'gemini', base: 'https://x' }), 'gemini');
  assert.strictEqual(app.providerKind({ base: 'https://generativelanguage.googleapis.com/v1beta' }), 'gemini');
  assert.strictEqual(app.providerKind({ name: 'gemini', base: 'https://x' }), 'gemini');
  assert.strictEqual(app.providerKind({ base: 'https://openrouter.ai/api/v1' }), 'openai');
  assert.strictEqual(app.providerKind({ kind: 'openai', base: 'https://generativelanguage.googleapis.com/v1beta' }), 'openai');
  assert.strictEqual(app.providerKind(null), 'openai');
});
console.log('\n' + passedReg + ' اختباراً للسجلّ ناجحاً');

/* ================= v3.4: أدوات التفويض والتقارير ================= */
let passedDel = 0;
async function okDel(name, fn) {
  try { await fn(); passedDel++; console.log('✔ [تفويض] ' + name); }
  catch (e) { console.error('✘ [تفويض] ' + name + ': ' + e.message); process.exitCode = 1; }
}

okDel('تعريفات الأدوات: الأسماء والمعاملات المطلوبة', () => {
  const byName = {};
  for (const tool of app.PC_DELEGATION_TOOLS) byName[tool.function.name] = tool;
  assert.deepStrictEqual(Object.keys(byName).sort(),
    ['pc_ask', 'pc_bots', 'pc_report', 'pc_task']);
  assert.deepStrictEqual(byName.pc_ask.function.parameters.required, ['bot', 'message']);
  assert.deepStrictEqual(byName.pc_task.function.parameters.required, ['bot', 'task']);
  assert.deepStrictEqual(byName.pc_bots.function.parameters.required, []);
  assert.deepStrictEqual(byName.pc_report.function.parameters.required, []);
  for (const n of Object.keys(byName)) {
    assert.strictEqual(byName[n].type, 'function');
    assert.ok(byName[n].function.parameters.properties.computer,
      n + ': معامل computer الاختياري موجود');
  }
});

okDel('formatPcReport: عدّادات وأسماء وآخر المهام', () => {
  const status = app.parseStatus({ app: 'Krouchi_DZ', version: '3.4.0',
    hostname: 'DESKTOP-1', uptime_s: 3661, disk: null, ram_mb: null });
  const tasks = app.parseTasks({ tasks: [
    { id: 3, bot_name: 'مساعد', title: 'مهمة أخيرة', status: 'done' },
    { id: 2, bot_name: 'مساعد', title: 'جارية', status: 'running' },
    { id: 1, bot_name: 'كاتب', title: 'قديمة', status: 'done' }] });
  const text = app.formatPcReport(status, tasks, 'Home PC');
  assert.ok(text.indexOf('Home PC') >= 0);
  assert.ok(text.indexOf('3.4.0') >= 0);
  assert.ok(text.indexOf('DESKTOP-1') >= 0);
  assert.ok(text.indexOf('1:01:01') >= 0);
  assert.ok(text.indexOf('done: 2') >= 0);
  assert.ok(text.indexOf('running: 1') >= 0);
  assert.ok(text.indexOf('مساعد [done] مهمة أخيرة') >= 0);
  assert.ok(text.indexOf('كاتب') >= 0);
});

/* نقل وهمي لخادم المرافقة: يوزّع بحسب المسار ويصفّي ردود المهام */
function fakePcTransport(script) {
  const state = { taskGets: 0 };
  return function (method, url, headers, body) {
    const path = url.replace(/^http:\/\/[^/]+/, '');
    const reply = (obj) => Promise.resolve(
      { status: 200, text: JSON.stringify(obj), error: '' });
    if (path === '/api/bots') {
      return reply({ bots: [{ id: 7, name: 'Helper', provider: 'p', model: 'm-x', mode: 'ask' }] });
    }
    if (path === '/api/status') {
      return reply({ app: 'Krouchi_DZ', version: '3.4.0', hostname: 'H1',
        uptime_s: 60, disk: null, ram_mb: null });
    }
    if (path === '/api/tasks' && method === 'GET') {
      return reply({ tasks: [{ id: 9, bot_id: 7, bot_name: 'Helper',
        title: 'قديمة', status: 'done', created_at: 'c' }] });
    }
    if (path === '/api/tasks' && method === 'POST') {
      return reply({ task: { id: 5, bot_id: 7, title: 'x',
        status: 'queued', created_at: 'c' } });
    }
    if (path === '/api/tasks/5') {
      state.taskGets++;
      const step = script[Math.min(state.taskGets - 1, script.length - 1)];
      return reply({ task: Object.assign(
        { id: 5, bot_id: 7, bot_name: 'Helper', title: 'x' }, step) });
    }
    if (path === '/api/chat') {
      return reply({ reply: 'جواب الحاسوب' });
    }
    return Promise.resolve({ status: 404, text: '{"error":"x"}', error: '' });
  };
}
const REG1 = [{ id: 'pc1', name: 'Home PC', host: '192.168.1.10',
  port: 8765, token: 'tok', mac: '' }];
const instantSleep = () => Promise.resolve();

(async () => {
  await okDel('pc_bots عبر نقل وهمي: سطور الاسم والنموذج', async () => {
    const out = await app.executePcTool('pc_bots', {},
      { registry: REG1, activeId: 'pc1', transport: fakePcTransport([]) });
    assert.strictEqual(out, 'Helper — m-x');
  });
  await okDel('pc_report عبر نقل وهمي: تقرير مدمج كامل', async () => {
    const out = await app.executePcTool('pc_report', {},
      { registry: REG1, activeId: 'pc1', transport: fakePcTransport([]) });
    assert.ok(out.indexOf('Home PC') >= 0);
    assert.ok(out.indexOf('done: 1') >= 0);
    assert.ok(out.indexOf('Helper') >= 0);
  });
  await okDel('pc_ask: يحلّ البوت بالاسم ويعيد الردّ', async () => {
    const out = await app.executePcTool('pc_ask',
      { bot: 'helper', message: 'سلام' },
      { registry: REG1, activeId: 'pc1', transport: fakePcTransport([]) });
    assert.strictEqual(out, 'جواب الحاسوب');
  });
  await okDel('pc_ask: بوت مجهول → نصّ خطأ بلا انهيار', async () => {
    const out = await app.executePcTool('pc_ask',
      { bot: 'Ghost', message: 'x' },
      { registry: REG1, activeId: 'pc1', transport: fakePcTransport([]) });
    assert.ok(out.indexOf('bot not found: Ghost') === 0);
  });
  await okDel('حاسوب مجهول → نصّ يسرد المتاح', async () => {
    const out = await app.executePcTool('pc_bots', { computer: 'Nope' },
      { registry: REG1, activeId: 'pc1', transport: fakePcTransport([]) });
    assert.ok(out.indexOf('computer not found: Nope') === 0);
    assert.ok(out.indexOf('Home PC') >= 0);
  });
  await okDel('pc_task: استطلاع created → running → done بالنتيجة', async () => {
    const transport = fakePcTransport([
      { status: 'running' },
      { status: 'done', result: 'النتيجة النهائية' }]);
    const out = await app.executePcTool('pc_task',
      { bot: 'Helper', task: 'نفّذ كذا' },
      { registry: REG1, activeId: 'pc1', transport,
        pollIntervalMs: 1, maxPollMs: 1000, sleep: instantSleep });
    assert.ok(out.indexOf('Task 5 done.') === 0, out);
    assert.ok(out.indexOf('النتيجة النهائية') >= 0);
  });
  await okDel('pc_task: تجاوز السقف وهو يعمل → ملاحظة ما زال يعمل', async () => {
    const transport = fakePcTransport([{ status: 'running' }]);
    const out = await app.executePcTool('pc_task',
      { bot: 'Helper', task: 'طويلة' },
      { registry: REG1, activeId: 'pc1', transport,
        pollIntervalMs: 10, maxPollMs: 30, sleep: instantSleep });
    assert.ok(out.indexOf('still running') >= 0, out);
  });
  await okDel('حلقة المحادثة بالأدوات: tool_calls تُنفَّذ ثم الردّ النهائي', async () => {
    const bodies = [];
    let calls = 0;
    const transport = (method, url, headers, body) => {
      calls++;
      bodies.push(JSON.parse(body));
      if (calls === 1) {
        return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
          choices: [{ message: { role: 'assistant', content: null,
            tool_calls: [{ id: 'c1', type: 'function',
              function: { name: 'pc_bots', arguments: '{}' } }] } }] }) });
      }
      return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
        choices: [{ message: { content: 'الردّ النهائي' } }] }) });
    };
    const seen = [];
    const reply = await app.sendChatWithTools('https://api.example.com/v1',
      'sk', 'm', [{ role: 'user', content: 'ما بوتات حاسوبي؟' }], {
        tools: app.PC_DELEGATION_TOOLS, transport,
        executeTool: (n, a) => { seen.push([n, a]); return Promise.resolve('Helper — m-x'); }
      });
    assert.strictEqual(reply, 'الردّ النهائي');
    assert.deepStrictEqual(seen, [['pc_bots', {}]]);
    assert.ok(Array.isArray(bodies[0].tools), 'الأدوات في الطلب الأول');
    const toolMsg = bodies[1].messages[bodies[1].messages.length - 1];
    assert.strictEqual(toolMsg.role, 'tool');
    assert.strictEqual(toolMsg.tool_call_id, 'c1');
    assert.strictEqual(toolMsg.content, 'Helper — m-x');
  });
  await okDel('inputComboBody: شكل combo كما في عقد الخادم', () => {
    assert.deepStrictEqual(app.inputComboBody(['ctrl', 'c']),
      { type: 'combo', keys: ['ctrl', 'c'] });
    assert.deepStrictEqual(app.inputComboBody(['ctrl', '']),
      { type: 'combo', keys: ['ctrl'] });
  });
  console.log('\n' + passedDel + ' اختباراً للتفويض ناجحاً');
})();

/* ================= v3.4: لوحة المفاتيح والواجهة ================= */
let passedKb = 0;
function okKb(name, fn) {
  try { fn(); passedKb++; console.log('✔ [لوحة/واجهة] ' + name); }
  catch (e) { console.error('✘ [لوحة/واجهة] ' + name + ': ' + e.message); process.exitCode = 1; }
}

okKb('KB_LAYOUTS: ثلاثة تخطيطات، كل مفتاح بعنوان وفعل صالح', () => {
  assert.deepStrictEqual(Object.keys(app.KB_LAYOUTS).sort(), ['ar', 'azerty', 'en']);
  const kinds = ['text', 'key', 'mod', 'space'];
  for (const name of Object.keys(app.KB_LAYOUTS)) {
    const layout = app.KB_LAYOUTS[name];
    assert.ok(Array.isArray(layout.rows) && layout.rows.length >= 6, name);
    for (const row of layout.rows) {
      assert.ok(Array.isArray(row) && row.length > 0, name + ': صف فارغ');
      for (const key of row) {
        assert.ok(typeof key.label === 'string' && key.label.length > 0,
          name + ': مفتاح بلا عنوان');
        assert.ok(key.act && kinds.indexOf(key.act.t) >= 0,
          name + ': فعل غير صالح ' + JSON.stringify(key.act));
        if (key.act.t !== 'space') {
          assert.ok(typeof key.act.v === 'string' && key.act.v.length > 0,
            name + ': فعل بلا قيمة');
        }
      }
    }
  }
});

okKb('KB_LAYOUTS: صفّ F فيه 12 مفتاحاً، والأسهم والمعدِّلات والمسافة موجودة', () => {
  for (const name of Object.keys(app.KB_LAYOUTS)) {
    const rows = app.KB_LAYOUTS[name].rows;
    const fRow = rows[0];
    assert.strictEqual(fRow.length, 12, name + ': صف F');
    fRow.forEach((key, i) => {
      assert.deepStrictEqual(key.act, { t: 'key', v: 'f' + (i + 1) });
    });
    const acts = [];
    rows.forEach((row) => row.forEach((key) => acts.push(key.act)));
    for (const arrow of ['left', 'up', 'down', 'right']) {
      assert.ok(acts.some((a) => a.t === 'key' && a.v === arrow),
        name + ': سهم ' + arrow);
    }
    for (const mod of ['ctrl', 'alt', 'shift', 'win']) {
      assert.ok(acts.some((a) => a.t === 'mod' && a.v === mod),
        name + ': معدِّل ' + mod);
    }
    assert.ok(acts.some((a) => a.t === 'space'), name + ': مسافة');
    for (const special of ['esc', 'tab', 'enter', 'backspace', 'delete',
        'home', 'end', 'pageup', 'pagedown']) {
      assert.ok(acts.some((a) => a.t === 'key' && a.v === special),
        name + ': خاص ' + special);
    }
  }
});

okKb('KB_LAYOUTS: صفوف الحروف بحسب التخطيط', () => {
  const texts = (layout) => {
    const out = [];
    app.KB_LAYOUTS[layout].rows.forEach((row) => row.forEach((key) => {
      if (key.act.t === 'text') out.push(key.act.v);
    }));
    return out;
  };
  assert.ok(texts('ar').indexOf('ض') >= 0 && texts('ar').indexOf('لا') >= 0);
  assert.ok(texts('azerty').indexOf('a') >= 0 && texts('azerty').indexOf('w') >= 0);
  assert.ok(texts('en').indexOf('q') >= 0 && texts('en').indexOf('m') >= 0);
});

okKb('markup v3.4: ملء الشاشة ولوحة المفاتيح والتقارير والسجلّ موجودة', () => {
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  const ids = ['screen-fullscreen', 'screen-kb', 'screen-kb-layout',
    'pc-select', 'pc-add', 'pc-delete', 'pc-name',
    'report-status', 'report-counts', 'report-tasks', 'report-refresh'];
  for (const id of ids) {
    assert.ok(html.indexOf('id="' + id + '"') >= 0, 'missing #' + id);
  }
  assert.ok(html.indexOf('screen-full') < 0 || html.indexOf('.screen-full') >= 0,
    'صنف screen-full معرّف في CSS');
});

okKb('markup v3.4: أقسام التحكّم اليدوي المحذوفة غائبة، والمُبقاة حاضرة', () => {
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  const removed = ['run-input', 'run-btn', 'run-output', 'open-input', 'open-btn',
    'open-status', 'shot-btn', 'shot-status', 'shot-img', 'clip-text', 'clip-get',
    'clip-set', 'clip-status', 'vol-down', 'vol-mute', 'vol-up',
    'windows-refresh', 'windows-list', 'proc-refresh', 'proc-list',
    'printer-select', 'printers-list'];
  for (const id of removed) {
    assert.ok(html.indexOf('id="' + id + '"') < 0, 'should be removed: #' + id);
  }
  const kept = ['pc-connected', 'pc-approvals-list', 'pc-bots-list',
    'pc-tasks-list', 'files-list', 'upload-input', 'pcScreenImg',
    'power-shutdown', 'power-restart', 'power-lock', 'power-sleep',
    'power-logoff', 'power-status', 'screen-text', 'screen-wheel-up'];
  for (const id of kept) {
    assert.ok(html.indexOf('id="' + id + '"') >= 0, 'kept missing: #' + id);
  }
});

okKb('الإصدار 3.4.0 في app.js و index.html ونصوص التنزيل باللغتين', () => {
  const js = fs.readFileSync(path.join(__dirname, 'assets', 'app.js'), 'utf8');
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  assert.ok(js.indexOf('3.4.0') >= 0, 'app.js');
  assert.ok(html.indexOf('3.4.0') >= 0, 'index.html');
  assert.ok(app.STRINGS.ar.about_p1.indexOf('3.4.0') >= 0);
  assert.ok(app.STRINGS.en.about_p1.indexOf('3.4.0') >= 0);
  assert.ok(app.STRINGS.ar.download_saved && app.STRINGS.en.download_saved);
  assert.ok(app.STRINGS.ar.download_failed && app.STRINGS.en.download_failed);
});
console.log('\n' + passedKb + ' اختباراً للوحة والواجهة ناجحاً');

/* ================= صور البوتات (v3.4): المعرض والتطبيع والعرض والمنتقي ================= */
let passedAv = 0;
function okAv(name, fn) {
  try { fn(); passedAv++; console.log('✔ [صور] ' + name); }
  catch (e) { console.error('✘ [صور] ' + name + ': ' + e.message); process.exitCode = 1; }
}

app.setLang('ar');

okAv('AVATAR_GALLERY: الأسماء الستّة بالترتيب تماماً', () =>
  assert.deepStrictEqual(app.AVATAR_GALLERY,
    ['bot_1.png', 'bot_2.png', 'bot_3.png', 'bot_4.png', 'bot_5.png', 'bot_6.png']));

okAv('normalizeBotAvatar: معرض يُحفظ، وكل ما عداه يصير فارغاً', () => {
  assert.strictEqual(app.normalizeBotAvatar('bot_3.png'), 'bot_3.png');
  assert.strictEqual(app.normalizeBotAvatar(''), '');
  assert.strictEqual(app.normalizeBotAvatar('evil.png'), '');
  assert.strictEqual(app.normalizeBotAvatar('🤖'), '');
  assert.strictEqual(app.normalizeBotAvatar(42), '');
  assert.strictEqual(app.normalizeBotAvatar(null), '');
  assert.strictEqual(app.normalizeBotAvatar(undefined), '');
});

okAv('normalizeBot: بوت قديم بلا avatar يحصل على فارغ وبقية الحقول تبقى', () => {
  assert.deepStrictEqual(
    app.normalizeBot({ id: 'b1', name: 'قديم', providerId: 'p', model: 'm' }),
    { id: 'b1', name: 'قديم', providerId: 'p', model: 'm', avatar: '' });
  assert.strictEqual(app.normalizeBot({ name: 'x', avatar: 'bot_5.png' }).avatar, 'bot_5.png');
  assert.strictEqual(app.normalizeBot({ name: 'x', avatar: 'bot_9.png' }).avatar, '');
  assert.strictEqual(app.normalizeBot(null), null);
});

okAv('loadBots: تطبيع عند التحميل من التخزين (قديم/صالح/فاسد)', () => {
  __lsStore['krouchi.bots.v1'] = JSON.stringify([
    { id: 'b1', name: 'قديم', providerId: 'p', model: 'm' },
    { id: 'b2', name: 'جديد', providerId: 'p', model: 'm', avatar: 'bot_4.png' },
    { id: 'b3', name: 'فاسد', providerId: 'p', model: 'm', avatar: 'evil.png' }]);
  const bots = app.loadBots();
  assert.deepStrictEqual(bots.map((b) => b.avatar), ['', 'bot_4.png', '']);
  delete __lsStore['krouchi.bots.v1'];
  assert.deepStrictEqual(app.loadBots(), []);
});

okAv('botAvatarHtml: صورة معرض → img بمسار صحيح و onerror ومونوغرام تحتها', () => {
  const html = app.botAvatarHtml({ name: 'مساعد', avatar: 'bot_3.png' });
  assert.ok(html.indexOf('<img class="bot-avatar') >= 0, html);
  assert.ok(html.indexOf('src="avatars/bot_3.png"') >= 0, html);
  assert.ok(html.indexOf('onerror=') >= 0, html);
  assert.ok(html.indexOf('bot-avatar-mono') >= 0, html);
});

okAv('botAvatarHtml: بلا صورة → مونوغرام بالحرف الصحيح (عربي ولاتيني مكبّر)', () => {
  const ar = app.botAvatarHtml({ name: 'مساعد', avatar: '' });
  assert.ok(ar.indexOf('bot-avatar-mono') >= 0 && ar.indexOf('>م<') >= 0, ar);
  assert.ok(ar.indexOf('<img') < 0, ar);
  const en = app.botAvatarHtml({ name: 'helper', avatar: '' });
  assert.ok(en.indexOf('>H<') >= 0, en);
  const empty = app.botAvatarHtml({ name: '', avatar: '' });
  assert.ok(empty.indexOf('>?</') >= 0, empty);
});

okAv('botAvatarHtml: اسم ملف مجهول أو قيمة إيموجي قديمة → مونوغرام بلا img', () => {
  for (const bad of ['bot_99.png', '🤖', 'https://x/y.png']) {
    const html = app.botAvatarHtml({ name: 'Bot', avatar: bad });
    assert.ok(html.indexOf('<img') < 0, bad + ' -> ' + html);
    assert.ok(html.indexOf('>B<') >= 0, html);
  }
});

okAv('parsePcBots: avatar يمرّ من حمولة الخادم ويُطبَّع', () => {
  assert.deepStrictEqual(
    app.parsePcBots({ bots: [
      { id: 1, name: 'أ', avatar: 'bot_2.png' },
      { id: 2, name: 'ب', avatar: 'قديم.png' },
      { id: 3, name: 'ج' }] }).map((b) => b.avatar),
    ['bot_2.png', '', '']);
});

okAv('avatarPickerHtml: 6 بلاطات معرض + بلاطة بدون صورة والاختيار محدّد', () => {
  const html = app.avatarPickerHtml('bot_2.png', 'مساعد');
  for (const f of app.AVATAR_GALLERY) {
    assert.ok(html.indexOf('data-avatar="' + f + '"') >= 0, f);
    assert.ok(html.indexOf('src="avatars/' + f + '"') >= 0, f);
  }
  assert.ok(html.indexOf('data-avatar=""') >= 0, 'none tile');
  assert.ok(html.indexOf(app.STRINGS.ar.avatar_none) >= 0, 'none label');
  assert.ok(html.indexOf('avatar-tile selected" data-avatar="bot_2.png"') >= 0,
    'selected ring on bot_2');
  const none = app.avatarPickerHtml('', 'مساعد');
  assert.ok(none.indexOf('avatar-tile avatar-tile-none selected') >= 0,
    'none tile selected when empty');
});

okAv('markup: حاوية المنتقي وترويسا المحادثة في الواجهة', () => {
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  assert.ok(html.indexOf('id="bot-avatar-picker"') >= 0, 'picker container');
  assert.ok(html.indexOf('data-i18n="avatar_label"') >= 0, 'picker label');
  assert.ok(html.indexOf('id="chat-bot-header"') >= 0, 'local chat header');
  assert.ok(html.indexOf('id="pc-chat-bot-header"') >= 0, 'pc chat header');
  assert.ok(html.indexOf('.bot-avatar') >= 0, 'avatar CSS');
  assert.ok(html.indexOf('.bot-avatar-mono') >= 0, 'monogram CSS');
});

okAv('حركة CSS: keyframes avatar-bob/avatar-bounce واحترام تقليل الحركة', () => {
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  assert.ok(/@keyframes avatar-bob/.test(html), 'avatar-bob keyframes');
  assert.ok(/@keyframes avatar-bounce/.test(html), 'avatar-bounce keyframes');
  assert.ok(html.indexOf('prefers-reduced-motion') >= 0, 'reduced-motion guard');
  assert.ok(html.indexOf('avatar-bob 3.2s') >= 0, 'bob applied');
  assert.ok(html.indexOf('.chat-bot-header') >= 0, 'scoped to chat headers');
});

okAv('ملفات المعرض الستّة موجودة في أصول التطبيق', () => {
  for (const f of app.AVATAR_GALLERY) {
    assert.ok(fs.existsSync(path.join(__dirname, 'assets', 'avatars', f)),
      'missing assets/avatars/' + f);
  }
});
console.log('\n' + passedAv + ' اختباراً للصور ناجحاً');

/* ================= v3.4: الواجهة المشتركة + موجّه الدور + حلقة التفويض الإلزامية ================= */
let passedShared = 0;
function okSh(name, fn) {
  try { fn(); passedShared++; console.log('✔ [مشتركة] ' + name); }
  catch (e) { console.error('✘ [مشتركة] ' + name + ': ' + e.message); process.exitCode = 1; }
}
async function okShAsync(name, fn) {
  try { await fn(); passedShared++; console.log('✔ [مشتركة] ' + name); }
  catch (e) { console.error('✘ [مشتركة] ' + name + ': ' + e.message); process.exitCode = 1; }
}
function clearSharedKeys() {
  delete __lsStore[app.LS_SHARED_API];
  delete __lsStore[app.LS_PROVIDERS];
  delete __lsStore[app.LS_BOTS];
  delete __lsStore[app.LS_CHATS];
}

app.setLang('ar');

okSh('تخزين الواجهة المشتركة: حفظ ثم تحميل (ذهاب وإياب)', () => {
  clearSharedKeys();
  assert.strictEqual(app.LS_SHARED_API, 'krouchi.sharedApi.v1');
  const saved = app.saveSharedApi({ providerId: 'p1', model: 'm-x' });
  assert.deepStrictEqual(saved, { providerId: 'p1', model: 'm-x' });
  assert.deepStrictEqual(JSON.parse(__lsStore['krouchi.sharedApi.v1']),
    { providerId: 'p1', model: 'm-x' });
  assert.deepStrictEqual(app.loadSharedApi(), { providerId: 'p1', model: 'm-x' });
  delete __lsStore[app.LS_SHARED_API];
  assert.strictEqual(app.loadSharedApi(), null);
});

okSh('هجرة: المزوّد ذو المفتاح يُفضَّل، والنموذج من أحدث بوت مستعمَل', () => {
  clearSharedKeys();
  app.saveProviders([
    { id: 'p1', name: 'nokey', base: 'https://a.example/v1', key: '', models: ['a1'] },
    { id: 'p2', name: 'keyed', base: 'https://b.example/v1', key: 'sk-2', models: ['b1', 'b2'] }]);
  app.saveBots([
    { id: 'bold', name: 'قديم', providerId: 'p2', model: 'model-old', system: '' },
    { id: 'bnew', name: 'جديد', providerId: 'p2', model: 'model-new', system: '' },
    { id: 'bother', name: 'آخر', providerId: 'p1', model: 'a1', system: '' }]);
  /* سجلّ المحادثات بترتيب الإدخال: محادثة الجديد أُنشئت بعد القديم */
  app.saveChats({
    bold: [{ role: 'user', content: 'س' }],
    bnew: [{ role: 'user', content: 'س' }, { role: 'assistant', content: 'ج' }] });
  const migrated = app.migrateSharedApi();
  assert.deepStrictEqual(migrated, { providerId: 'p2', model: 'model-new' });
  assert.deepStrictEqual(app.loadSharedApi(), { providerId: 'p2', model: 'model-new' });
});

okSh('هجرة: بلا سجلّ محادثات → نموذج أول بوت مرتبط بالمزوّد', () => {
  clearSharedKeys();
  app.saveProviders([
    { id: 'p1', name: 'one', base: 'https://a.example/v1', key: 'sk', models: ['m1', 'm2'] }]);
  app.saveBots([
    { id: 'b1', name: 'أول', providerId: 'p1', model: 'm-first', system: '' },
    { id: 'b2', name: 'ثانٍ', providerId: 'p1', model: 'm-second', system: '' }]);
  app.saveChats({});
  assert.deepStrictEqual(app.migrateSharedApi(),
    { providerId: 'p1', model: 'm-first' });
});

okSh('هجرة: لا مفتاح عند أي مزوّد → الأول، وبلا بوتات مرتبطة → نموذج فارغ', () => {
  clearSharedKeys();
  app.saveProviders([
    { id: 'p1', name: 'one', base: 'https://a.example/v1', key: '', models: ['m1'] },
    { id: 'p2', name: 'two', base: 'https://b.example/v1', key: '', models: ['m2'] }]);
  app.saveBots([]);
  assert.deepStrictEqual(app.migrateSharedApi(), { providerId: 'p1', model: '' });
});

okSh('هجرة: بلا مزوّدين → تبقى الواجهة غير مضبوطة ولا يُكتَب شيء', () => {
  clearSharedKeys();
  app.saveProviders([]);
  assert.strictEqual(app.migrateSharedApi(), null);
  assert.strictEqual(app.loadSharedApi(), null);
  assert.ok(!(app.LS_SHARED_API in __lsStore), 'لا كتابة في التخزين');
});

okSh('هجرة: واجهة مشتركة موجودة لا تُستبدَل', () => {
  clearSharedKeys();
  app.saveProviders([
    { id: 'p9', name: 'x', base: 'https://x.example/v1', key: 'sk', models: ['mx'] }]);
  app.saveSharedApi({ providerId: 'keep', model: 'keep-model' });
  assert.deepStrictEqual(app.migrateSharedApi(),
    { providerId: 'keep', model: 'keep-model' });
});

okSh('موجّه الدور: الثوابت تحمل أسماء الأدوات وعبارة عدم النفي باللغتين', () => {
  for (const tool of ['pc_bots', 'pc_ask', 'pc_task', 'pc_report']) {
    assert.ok(app.ROLE_PROMPT_AR.indexOf(tool) >= 0, 'ar: ' + tool);
    assert.ok(app.ROLE_PROMPT_EN.indexOf(tool) >= 0, 'en: ' + tool);
  }
  assert.ok(app.ROLE_PROMPT_AR.indexOf('لا تستطيع التواصل مع بوتات الحاسوب') >= 0);
  assert.ok(app.ROLE_PROMPT_AR.indexOf('لا تقل أبداً') >= 0);
  assert.ok(app.ROLE_PROMPT_EN.indexOf(
    'never say you cannot communicate with the computer bots') >= 0);
  assert.strictEqual(app.getRolePrompt('ar'), app.ROLE_PROMPT_AR);
  assert.strictEqual(app.getRolePrompt('en'), app.ROLE_PROMPT_EN);
});

okSh('موجّه الدور: التركيب = الدور ثم تعليمات البوت، وبلا تعليمات الدور وحده', () => {
  assert.strictEqual(
    app.composeSystemContent({ system: 'تعليماتي الخاصة' }),
    app.ROLE_PROMPT_AR + '\n\n' + 'تعليماتي الخاصة');
  assert.strictEqual(app.composeSystemContent({ system: '' }), app.ROLE_PROMPT_AR);
  assert.strictEqual(app.composeSystemContent({}), app.ROLE_PROMPT_AR);
  assert.strictEqual(
    app.composeSystemContent({ system: 'Mine' }, 'en'),
    app.ROLE_PROMPT_EN + '\n\n' + 'Mine');
  const convo = app.buildLocalConvo({ system: 'S' }, [{ role: 'user', content: 'hi' }]);
  assert.strictEqual(convo[0].role, 'system');
  assert.strictEqual(convo[0].content, app.ROLE_PROMPT_AR + '\n\n' + 'S');
  assert.deepStrictEqual(convo[1], { role: 'user', content: 'hi' });
});

okSh('markup: نموذج البوت بلا منتقي مزوّد/نموذج، وسطر الواجهة وقسمها موجودان', () => {
  const html = fs.readFileSync(path.join(__dirname, 'assets', 'index.html'), 'utf8');
  assert.ok(html.indexOf('id="bot-provider"') < 0, 'bot-provider removed');
  assert.ok(html.indexOf('id="bot-model"') < 0, 'bot-model removed');
  assert.ok(html.indexOf('id="bot-models"') < 0, 'bot-models removed');
  assert.ok(html.indexOf('id="bot-shared-line"') >= 0, 'shared line present');
  assert.ok(html.indexOf('id="bot-shared-change"') >= 0, 'shared change button');
  assert.ok(html.indexOf('id="shared-provider"') >= 0, 'shared provider select');
  assert.ok(html.indexOf('id="shared-model"') >= 0, 'shared model select');
  assert.ok(html.indexOf('id="shared-save"') >= 0, 'shared save button');
});

(async () => {
  await okShAsync('الحلّ وقت الإرسال: ربط البوت القديم مُتجاهَل والواجهة المشتركة تُستعمل', async () => {
    clearSharedKeys();
    app.setLang('ar');
    app.saveProviders([
      { id: 'pStale', name: 'stale', base: 'https://stale.example/v1', key: 'sk-stale', models: ['stale-model'] },
      { id: 'pShared', name: 'sharedprov', base: 'https://shared.example/v1', key: 'sk-shared', models: ['shared-model'] }]);
    app.saveSharedApi({ providerId: 'pShared', model: 'shared-model' });
    const bot = { id: 'b1', name: 'نائب', providerId: 'pStale', model: 'stale-model',
      system: 'تعليمات البوت الخاصة' };
    const seen = {};
    const transport = (method, url, headers, body) => {
      Object.assign(seen, { method, url, headers, body: JSON.parse(body) });
      return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
        choices: [{ message: { content: 'رد بالواجهة المشتركة' } }] }) });
    };
    const reply = await app.sendLocalBotChat(bot,
      [{ role: 'user', content: 'مرحباً' }], { transport, registry: [] });
    assert.strictEqual(reply, 'رد بالواجهة المشتركة');
    assert.strictEqual(seen.url, 'https://shared.example/v1/chat/completions');
    assert.strictEqual(seen.headers.Authorization, 'Bearer sk-shared');
    assert.strictEqual(seen.body.model, 'shared-model');
    assert.strictEqual(seen.body.messages[0].role, 'system');
    assert.strictEqual(seen.body.messages[0].content,
      app.ROLE_PROMPT_AR + '\n\n' + 'تعليمات البوت الخاصة');
    assert.deepStrictEqual(seen.body.messages[1], { role: 'user', content: 'مرحباً' });
  });

  await okShAsync('لا واجهة مشتركة: الإرسال يرفض بـ err_shared_api وبلا أي نداء للمزوّد', async () => {
    clearSharedKeys();
    app.saveProviders([
      { id: 'p1', name: 'one', base: 'https://a.example/v1', key: 'sk', models: ['m'] }]);
    let calls = 0;
    const transport = () => { calls++; return Promise.resolve(
      { status: 200, text: '{}', error: '' }); };
    let err = null;
    try {
      await app.sendLocalBotChat({ id: 'b1', name: 'x', system: '' },
        [{ role: 'user', content: 'hi' }], { transport, registry: [] });
    } catch (e) { err = e; }
    assert.ok(err, 'رفض متوقع');
    assert.strictEqual(err.kind, 'shared_api');
    assert.strictEqual(err.message, app.t('err_shared_api'));
    assert.strictEqual(calls, 0, 'لا نداء للمزوّد إطلاقاً');
  });

  await okShAsync('واجهة مشتركة ناقصة: مزوّد محذوف أو نموذج فارغ → رفض بلا نداء', async () => {
    clearSharedKeys();
    app.saveProviders([
      { id: 'p1', name: 'one', base: 'https://a.example/v1', key: 'sk', models: ['m'] }]);
    let calls = 0;
    const transport = () => { calls++; return Promise.resolve(
      { status: 200, text: '{}', error: '' }); };
    const bot = { id: 'b1', name: 'x', system: '' };
    const hist = [{ role: 'user', content: 'hi' }];
    app.saveSharedApi({ providerId: 'gone', model: 'm' });
    await assert.rejects(
      app.sendLocalBotChat(bot, hist, { transport, registry: [] }),
      (e) => e.kind === 'shared_api');
    app.saveSharedApi({ providerId: 'p1', model: '' });
    await assert.rejects(
      app.sendLocalBotChat(bot, hist, { transport, registry: [] }),
      (e) => e.kind === 'shared_api');
    assert.strictEqual(calls, 0);
  });

  await okShAsync('delegation loop: pc_task executed and result fed back', async () => {
    clearSharedKeys();
    app.setLang('ar');
    app.saveProviders([
      { id: 'pShared', name: 'sharedprov', base: 'https://shared.example/v1',
        key: 'sk-shared', models: ['shared-model'] }]);
    app.saveSharedApi({ providerId: 'pShared', model: 'shared-model' });
    const registry = [{ id: 'pc1', name: 'Home PC', host: '192.168.1.10',
      port: 8765, token: 'tok', mac: '' }];
    /* نقل حاسوب وهمي: إنشاء المهمة يُلتقَط، وأول استطلاع يعيد done */
    let creation = null;
    const pcTransport = (method, url, headers, body) => {
      const pth = url.replace(/^http:\/\/[^/]+/, '');
      const reply = (obj) => Promise.resolve(
        { status: 200, text: JSON.stringify(obj), error: '' });
      if (pth === '/api/bots') {
        return reply({ bots: [{ id: 7, name: 'Helper', provider: 'p', model: 'm-x', mode: 'ask' }] });
      }
      if (pth === '/api/tasks' && method === 'POST') {
        creation = { method, url, body: JSON.parse(body) };
        return reply({ task: { id: 5, bot_id: 7, title: 'x', status: 'queued', created_at: 'c' } });
      }
      if (pth === '/api/tasks/5') {
        return reply({ task: { id: 5, bot_id: 7, bot_name: 'Helper', title: 'x',
          status: 'done', result: 'نتيجة المهمة على الحاسوب' } });
      }
      return Promise.resolve({ status: 404, text: '{"error":"x"}', error: '' });
    };
    /* نقل مزوّد مكتوب: أول ردّ يطلب pc_task، والثاني هو الجواب النهائي */
    const bodies = [];
    const urls = [];
    let calls = 0;
    const providerTransport = (method, url, headers, body) => {
      calls++;
      urls.push(url);
      bodies.push(JSON.parse(body));
      if (calls === 1) {
        return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
          choices: [{ message: { role: 'assistant', content: null,
            tool_calls: [{ id: 'tc1', type: 'function',
              function: { name: 'pc_task',
                arguments: '{"bot":"Helper","task":"لخّص ملف الملاحظات"}' } }] } }] }) });
      }
      return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
        choices: [{ message: { content: 'أنجز بوت الحاسوب المهمة' } }] }) });
    };
    const bot = { id: 'b1', name: 'نائب', providerId: 'pStale', model: 'stale', system: '' };
    const reply = await app.sendLocalBotChat(bot,
      [{ role: 'user', content: 'كلّف حاسوبي بمهمة' }],
      { transport: providerTransport, pcTransport, registry, activeId: 'pc1' });
    /* (أ) الحاسوب تلقّى إنشاء المهمة للبوت الصحيح بالنصّ الصحيح */
    assert.ok(creation, 'أُنشئت مهمة على الحاسوب');
    assert.strictEqual(creation.url, 'http://192.168.1.10:8765/api/tasks');
    assert.strictEqual(creation.body.bot_id, 7);
    assert.ok(creation.body.prompt.indexOf('لخّص ملف الملاحظات') >= 0);
    /* الطلب الأول بالواجهة المشتركة وبالأدوات وموجّه الدور */
    assert.strictEqual(urls[0], 'https://shared.example/v1/chat/completions');
    assert.strictEqual(bodies[0].model, 'shared-model');
    assert.ok(Array.isArray(bodies[0].tools), 'الأدوات في الطلب الأول');
    assert.strictEqual(bodies[0].messages[0].content, app.ROLE_PROMPT_AR);
    /* (ب) الطلب الثاني يحمل رسالة نتيجة الأداة بنتيجة المهمة */
    const toolMsgs = bodies[1].messages.filter((m) => m.role === 'tool');
    assert.strictEqual(toolMsgs.length, 1);
    assert.strictEqual(toolMsgs[0].tool_call_id, 'tc1');
    assert.ok(toolMsgs[0].content.indexOf('Task 5 done.') === 0, toolMsgs[0].content);
    assert.ok(toolMsgs[0].content.indexOf('نتيجة المهمة على الحاسوب') >= 0);
    /* (ج) الجواب النهائي من ردّ المتابعة */
    assert.strictEqual(reply, 'أنجز بوت الحاسوب المهمة');
  });

  await okShAsync('بوّابة التفويض: مزوّد مشترك gemini → إرسال عادٍ بلا أدوات', async () => {
    clearSharedKeys();
    app.saveProviders([
      { id: 'pGem', name: 'gemini', base: 'https://generativelanguage.googleapis.com/v1beta',
        key: 'k', kind: 'gemini', models: ['gemini-x'] }]);
    app.saveSharedApi({ providerId: 'pGem', model: 'gemini-x' });
    const registry = [{ id: 'pc1', name: 'Home PC', host: '192.168.1.10',
      port: 8765, token: 'tok', mac: '' }];
    const bodies = [];
    const transport = (method, url, headers, body) => {
      bodies.push(JSON.parse(body));
      return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
        choices: [{ message: { content: 'رد عادي' } }] }) });
    };
    const reply = await app.sendLocalBotChat({ id: 'b1', name: 'x', system: '' },
      [{ role: 'user', content: 'hi' }], { transport, registry, activeId: 'pc1' });
    assert.strictEqual(reply, 'رد عادي');
    assert.strictEqual(bodies.length, 1);
    assert.ok(!('tools' in bodies[0]), 'لا أدوات مع gemini');
    assert.strictEqual(bodies[0].messages[0].content, app.ROLE_PROMPT_AR);
  });

  clearSharedKeys();
  console.log('\n' + passedShared + ' اختباراً للواجهة المشتركة ناجحاً');
})();
