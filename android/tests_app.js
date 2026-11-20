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
    [{ id: '7', name: 'مساعد', provider: 'openrouter', model: 'm', mode: 'ask' }]));
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
