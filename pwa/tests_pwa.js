/* Krouchi_DZ PWA — unit tests (Node). Run: node tests_pwa.js
 * Covers: the fetch transport that replaces the native bridge in a
 * browser, the web app manifest, the service worker shell list,
 * the PWA markup in index.html, and a regression subset of the
 * phone UI's pure functions running against the PWA copy of app.js.
 */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const DIR = __dirname;

/* localStorage stub must exist before app.js loads (language state) */
const __lsStore = {};
global.localStorage = {
  getItem: (k) => (k in __lsStore ? __lsStore[k] : null),
  setItem: (k, v) => { __lsStore[k] = String(v); },
  removeItem: (k) => { delete __lsStore[k]; }
};

const app = require('./app.js');

let passed = 0;
let failed = 0;
function ok(name, fn) {
  try { fn(); passed++; console.log('PASS ' + name); }
  catch (e) { failed++; console.error('FAIL ' + name + ': ' + e.message); }
}
async function okAsync(name, fn) {
  try { await fn(); passed++; console.log('PASS ' + name); }
  catch (e) { failed++; console.error('FAIL ' + name + ': ' + e.message); }
}
function throwsKind(fn, kind) {
  try { fn(); } catch (e) { assert.strictEqual(e.kind, kind, 'kind=' + e.kind); return; }
  throw new Error('no error thrown');
}
async function rejectsKind(promise, kind) {
  try { await promise; } catch (e) { assert.strictEqual(e.kind, kind, 'kind=' + e.kind); return; }
  throw new Error('promise did not reject');
}

/* ---------- mock fetch ---------- */
function fakeResponse(status, bodyText) {
  return { status: status, ok: status >= 200 && status < 300,
           text: () => Promise.resolve(bodyText) };
}
function mockFetch(handler) {
  const calls = [];
  const fn = function (url, opts) {
    calls.push({ url: url, opts: opts || {} });
    return handler(url, opts || {});
  };
  fn.calls = calls;
  return fn;
}

(async () => {

/* ================= fetch transport ================= */

await okAsync('fetchTransport: success shape mirrors the bridge result', async () => {
  const f = mockFetch(() => Promise.resolve(fakeResponse(200, '{"a":1}')));
  const res = await app.fetchTransport('GET', 'https://x.test/v1/models',
    { Authorization: 'Bearer k' }, '', null, f);
  assert.deepStrictEqual(res, { status: 200, text: '{"a":1}', error: '' });
  assert.strictEqual(f.calls[0].url, 'https://x.test/v1/models');
  assert.strictEqual(f.calls[0].opts.method, 'GET');
  assert.strictEqual(f.calls[0].opts.headers.Authorization, 'Bearer k');
  assert.ok(f.calls[0].opts.signal, 'an AbortSignal is passed for timeouts');
});

await okAsync('fetchTransport: HTTP error status is passed through, not thrown', async () => {
  const f = mockFetch(() => Promise.resolve(fakeResponse(500, 'oops')));
  const res = await app.fetchTransport('GET', 'https://x.test/', {}, '', null, f);
  assert.strictEqual(res.status, 500);
  assert.strictEqual(res.text, 'oops');
});

await okAsync('fetchTransport: network failure -> status 0 with error text', async () => {
  const f = mockFetch(() => Promise.reject(new Error('boom')));
  const res = await app.fetchTransport('GET', 'https://x.test/', {}, '', null, f);
  assert.strictEqual(res.status, 0);
  assert.ok(res.error.indexOf('boom') >= 0);
});

await okAsync('fetchTransport: timeout aborts and maps to error timeout', async () => {
  const f = mockFetch((url, opts) => new Promise((resolve, reject) => {
    opts.signal.addEventListener('abort', () => reject(new Error('AbortError')));
  }));
  const res = await app.fetchTransport('GET', 'https://x.test/slow', {}, '', 40, f);
  assert.deepStrictEqual(res, { status: 0, text: '', error: 'timeout' });
});

await okAsync('fetchTransport: POST body is sent verbatim', async () => {
  const f = mockFetch(() => Promise.resolve(fakeResponse(200, '{}')));
  await app.fetchTransport('POST', 'https://x.test/v1/chat/completions',
    { 'Content-Type': 'application/json' }, '{"model":"m"}', null, f);
  assert.strictEqual(f.calls[0].opts.method, 'POST');
  assert.strictEqual(f.calls[0].opts.body, '{"model":"m"}');
});

/* httpRequest (the UI entry point) must take the fetch path when no
 * native bridge exists — in Node there is no window.KrouchiBridge. */
await okAsync('httpRequest: uses fetch when the bridge is absent', async () => {
  const f = mockFetch(() => Promise.resolve(fakeResponse(200, 'hello')));
  const saved = global.fetch;
  global.fetch = f;
  try {
    const res = await app.httpRequest('GET', 'https://x.test/ping', {}, '');
    assert.deepStrictEqual(res, { status: 200, text: 'hello', error: '' });
  } finally { global.fetch = saved; }
});

/* ================= discovery + chat over the fetch transport ================= */

await okAsync('discoverModels: GET {base}/models with Bearer key, ids parsed', async () => {
  const f = mockFetch(() => Promise.resolve(fakeResponse(200,
    JSON.stringify({ data: [{ id: 'a' }, { id: 'b' }, { id: 'a' }] }))));
  const saved = global.fetch;
  global.fetch = f;
  try {
    const models = await app.discoverModels('https://api.example.com/v1', 'sk-123');
    assert.deepStrictEqual(models, ['a', 'b']);
    assert.strictEqual(f.calls[0].url, 'https://api.example.com/v1/models');
    assert.strictEqual(f.calls[0].opts.method, 'GET');
    assert.strictEqual(f.calls[0].opts.headers.Authorization, 'Bearer sk-123');
  } finally { global.fetch = saved; }
});

await okAsync('discoverModels: 401 -> kind auth', async () => {
  const saved = global.fetch;
  global.fetch = mockFetch(() => Promise.resolve(fakeResponse(401, 'no')));
  try {
    await rejectsKind(app.discoverModels('https://api.example.com/v1', 'bad'), 'auth');
  } finally { global.fetch = saved; }
});

await okAsync('discoverModels: network failure -> kind unreachable', async () => {
  const saved = global.fetch;
  global.fetch = mockFetch(() => Promise.reject(new Error('down')));
  try {
    await rejectsKind(app.discoverModels('https://api.example.com/v1', 'k'), 'unreachable');
  } finally { global.fetch = saved; }
});

await okAsync('discoverModels: non-JSON reply -> kind not_json', async () => {
  const saved = global.fetch;
  global.fetch = mockFetch(() => Promise.resolve(fakeResponse(200, '<html>')));
  try {
    await rejectsKind(app.discoverModels('https://api.example.com/v1', 'k'), 'not_json');
  } finally { global.fetch = saved; }
});

await okAsync('sendChat: POST {base}/chat/completions, OpenAI body, reply parsed', async () => {
  const f = mockFetch(() => Promise.resolve(fakeResponse(200,
    JSON.stringify({ choices: [{ message: { content: 'Hi there' } }] }))));
  const saved = global.fetch;
  global.fetch = f;
  try {
    const reply = await app.sendChat('https://api.example.com/v1/', 'sk-9', 'model-x',
      [{ role: 'user', content: 'hello' }]);
    assert.strictEqual(reply, 'Hi there');
    assert.strictEqual(f.calls[0].url, 'https://api.example.com/v1/chat/completions');
    assert.strictEqual(f.calls[0].opts.method, 'POST');
    assert.strictEqual(f.calls[0].opts.headers.Authorization, 'Bearer sk-9');
    assert.strictEqual(f.calls[0].opts.headers['Content-Type'], 'application/json');
    assert.deepStrictEqual(JSON.parse(f.calls[0].opts.body),
      { model: 'model-x', messages: [{ role: 'user', content: 'hello' }] });
  } finally { global.fetch = saved; }
});

await okAsync('sendChat: 500 -> kind http', async () => {
  const saved = global.fetch;
  global.fetch = mockFetch(() => Promise.resolve(fakeResponse(500, 'err')));
  try {
    await rejectsKind(app.sendChat('https://a.test/v1', 'k', 'm', []), 'http');
  } finally { global.fetch = saved; }
});

/* ================= manifest ================= */

function pngSize(file) {
  const buf = fs.readFileSync(file);
  assert.strictEqual(buf.toString('ascii', 1, 4), 'PNG', file + ' is not a PNG');
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

let manifest = null;
ok('manifest.webmanifest parses as JSON', () => {
  manifest = JSON.parse(fs.readFileSync(path.join(DIR, 'manifest.webmanifest'), 'utf8'));
});

ok('manifest: required fields and app-matching colors', () => {
  assert.strictEqual(manifest.name, 'Krouchi_DZ');
  assert.strictEqual(manifest.short_name, 'Krouchi_DZ');
  assert.strictEqual(manifest.display, 'standalone');
  assert.strictEqual(manifest.theme_color, '#1565C0');
  assert.strictEqual(manifest.background_color, '#f4f6f8');
  assert.ok(manifest.start_url, 'start_url present');
});

ok('manifest: every icon exists on disk with the declared size', () => {
  assert.ok(Array.isArray(manifest.icons) && manifest.icons.length >= 3);
  for (const icon of manifest.icons) {
    const file = path.join(DIR, icon.src);
    assert.ok(fs.existsSync(file), icon.src + ' missing');
    const declared = parseInt(icon.sizes.split('x')[0], 10);
    const actual = pngSize(file);
    assert.strictEqual(actual.width, declared, icon.src + ' width');
    assert.strictEqual(actual.height, declared, icon.src + ' height');
  }
  const purposes = manifest.icons.map((i) => i.purpose);
  assert.ok(purposes.indexOf('maskable') >= 0, 'a maskable icon is declared');
});

ok('apple-touch-icon.png is 180x180', () => {
  assert.deepStrictEqual(pngSize(path.join(DIR, 'apple-touch-icon.png')),
    { width: 180, height: 180 });
});

/* ================= service worker ================= */

ok('sw.js exists and parses as JavaScript', () => {
  const src = fs.readFileSync(path.join(DIR, 'sw.js'), 'utf8');
  new Function(src.replace(/'use strict';/, '')); // syntax check only
});

ok('sw.js: shell asset list matches real files', () => {
  const src = fs.readFileSync(path.join(DIR, 'sw.js'), 'utf8');
  const m = src.match(/SHELL_ASSETS\s*=\s*\[([\s\S]*?)\]/);
  assert.ok(m, 'SHELL_ASSETS array found');
  const assets = Array.from(m[1].matchAll(/'([^']+)'/g)).map((x) => x[1]);
  assert.ok(assets.length >= 6, 'shell lists at least 6 assets');
  for (const a of assets) {
    if (a === './') continue;
    const file = path.join(DIR, a.replace(/^\.\//, ''));
    assert.ok(fs.existsSync(file), 'shell asset missing: ' + a);
  }
});

ok('sw.js: never caches provider traffic (no API paths, origin guard)', () => {
  const src = fs.readFileSync(path.join(DIR, 'sw.js'), 'utf8');
  assert.ok(src.indexOf('chat/completions') < 0, 'no chat endpoint in sw');
  assert.ok(src.indexOf('/models') < 0, 'no models endpoint in sw');
  assert.ok(src.indexOf('url.origin !== self.location.origin') >= 0,
    'cross-origin requests are passed through');
});

/* ================= index.html PWA markup ================= */

const html = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');

ok('index.html: manifest link, theme-color and Apple PWA tags present', () => {
  assert.ok(html.indexOf('<link rel="manifest" href="manifest.webmanifest">') >= 0);
  assert.ok(html.indexOf('name="theme-color" content="#1565C0"') >= 0);
  assert.ok(html.indexOf('name="apple-mobile-web-app-capable" content="yes"') >= 0);
  assert.ok(html.indexOf('name="apple-mobile-web-app-status-bar-style"') >= 0);
  assert.ok(html.indexOf('<link rel="apple-touch-icon" href="apple-touch-icon.png">') >= 0);
});

ok('index.html: registers the service worker and loads app.js', () => {
  assert.ok(html.indexOf("navigator.serviceWorker.register('sw.js')") >= 0);
  assert.ok(html.indexOf('<script src="app.js"></script>') >= 0);
});

ok('index.html: authorship line kept verbatim (ar + en strings ship in app.js)', () => {
  assert.ok(html.indexOf('data-i18n="about_author"') >= 0);
  const js = fs.readFileSync(path.join(DIR, 'app.js'), 'utf8');
  assert.ok(js.indexOf('تأليف: كروشي عبد الرزاق') >= 0, 'Arabic author line');
  assert.ok(js.indexOf('By Krouchi Abderrazak') >= 0, 'English author line');
});

ok('pwa folder: no forbidden origin mentions anywhere', () => {
  for (const f of ['index.html', 'app.js', 'sw.js', 'manifest.webmanifest', 'README.md']) {
    const text = fs.readFileSync(path.join(DIR, f), 'utf8');
    assert.ok(!/MausBot/i.test(text), f + ' must not mention MausBot');
    assert.ok(!/\bREA\b/.test(text), f + ' must not mention REA');
  }
});

/* ================= regression subset: pure UI functions ================= */

ok('regression: normalizeBaseUrl mirrors the phone UI', () => {
  assert.strictEqual(app.normalizeBaseUrl('api.deepseek.com'), 'https://api.deepseek.com/v1');
  assert.strictEqual(app.normalizeBaseUrl('https://openrouter.ai/api/v1/'), 'https://openrouter.ai/api/v1');
  assert.strictEqual(app.normalizeBaseUrl('https://api.z.ai/api/paas/v4/chat/completions'), 'https://api.z.ai/api/paas/v4');
  throwsKind(() => app.normalizeBaseUrl(''), 'bad_url');
});

ok('regression: deriveName + parseModelsOpenAI', () => {
  assert.strictEqual(app.deriveName('https://api.deepseek.com/v1'), 'deepseek');
  assert.deepStrictEqual(app.parseModelsOpenAI({ data: [{ id: 'a' }, { id: 'a' }] }), ['a']);
  throwsKind(() => app.parseModelsOpenAI({ data: [] }), 'empty');
});

ok('regression: buildChatBody + parseChatReply + httpErrorFor', () => {
  assert.strictEqual(app.buildChatBody('m', [{ role: 'user', content: 'hi' }]),
    '{"model":"m","messages":[{"role":"user","content":"hi"}]}');
  assert.strictEqual(app.parseChatReply({ choices: [{ message: { content: 'x' } }] }), 'x');
  throwsKind(() => { throw app.httpErrorFor(403); }, 'auth');
});

ok('regression: PC companion helpers unchanged', () => {
  assert.strictEqual(app.pcBaseUrl({ host: '192.168.1.10' }), 'http://192.168.1.10:8765');
  const r = app.buildPcRequest({ host: 'h', token: 'tok' }, 'GET', '/api/ping');
  assert.strictEqual(r.headers['X-Krouchi-Token'], 'tok');
  assert.deepStrictEqual(app.pcDecisionBody('whatever'), { decision: 'deny' });
});

ok('regression: i18n parity between ar and en, ar default', () => {
  assert.deepStrictEqual(app.SUPPORTED_LANGS, ['ar', 'en']);
  assert.deepStrictEqual(Object.keys(app.STRINGS.en).sort(),
    Object.keys(app.STRINGS.ar).sort());
  app.setLang('en');
  assert.strictEqual(app.t('btn_send'), 'Send');
  app.setLang('ar');
  assert.strictEqual(app.t('btn_send'), 'إرسال');
});

console.log('\n' + passed + ' passed, ' + failed + ' failed');
if (failed) process.exitCode = 1;
})();
ok('معرّف بوت نصّي رقمي يُحوَّل إلى رقم (إصلاح HTTP 400)', () => {
  assert.deepStrictEqual(app.pcChatBody('3', 'سلام'), { bot_id: 3, text: 'سلام' });
  assert.deepStrictEqual(app.pcChatBody(3, 'سلام'), { bot_id: 3, text: 'سلام' });
});
