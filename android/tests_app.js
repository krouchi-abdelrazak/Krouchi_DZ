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
  assert.deepStrictEqual(saved, { host: '192.168.1.20', port: 8765, token: 'abc' });
  assert.deepStrictEqual(app.loadPcConfig(), saved);
});
okPc('تطبيع الإعدادات: منفذ نصي وفراغات', () =>
  assert.deepStrictEqual(
    app.normalizePcConfig({ host: ' h ', port: '9001', token: ' t ' }),
    { host: 'h', port: 9001, token: 't' }));

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
