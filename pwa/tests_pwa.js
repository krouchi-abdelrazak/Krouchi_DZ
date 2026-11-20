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

/* ================= v3.2: approval-denied mapping ================= */

await okAsync('pcRequest: 403 with a denied body -> kind denied', async () => {
  const transport = () => Promise.resolve(
    { status: 403, text: '{"error":"denied"}', error: '' });
  await rejectsKind(app.pcRequest({ host: 'h', token: 't' }, 'POST',
    '/api/run', app.runBody('dir'), null, transport), 'denied');
});

await okAsync('pcRequest: plain 403 -> kind auth (bad token)', async () => {
  const transport = () => Promise.resolve(
    { status: 403, text: '', error: '' });
  await rejectsKind(app.pcRequest({ host: 'h', token: 't' }, 'GET',
    '/api/bots', null, null, transport), 'auth');
});

await okAsync('pcRequest: task creation body + detail parse', async () => {
  const transport = (method, url, headers, body) => {
    assert.ok(url.endsWith('/api/tasks'), 'tasks URL');
    assert.deepStrictEqual(JSON.parse(body),
      { bot_id: 3, title: 'T', prompt: 'P' });
    return Promise.resolve({ status: 200, error: '',
      text: '{"task":{"id":9,"title":"T","status":"queued"}}' });
  };
  const data = await app.pcRequest({ host: 'h', token: 't' }, 'POST',
    '/api/tasks', app.taskBody('3', 'T', 'P'), null, transport);
  const created = app.parseTaskDetail(data);
  assert.strictEqual(created.id, '9');
  assert.strictEqual(created.status, 'queued');
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
/* ================= v3.2: tasks + full control helpers ================= */

ok('v3.2 markup (v3.4-converted): kept tasks/control sections exist in index.html', () => {
  const html32 = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  const ids = ['pc-tasks-wrap', 'task-bot', 'task-title', 'task-prompt',
    'task-create', 'task-status', 'pc-tasks-list', 'pc-task-detail',
    'task-detail-title', 'task-cancel', 'task-back', 'pc-control-wrap',
    'pc-status-fields', 'status-refresh', 'files-path', 'files-up',
    'files-list', 'files-status', 'upload-input', 'upload-status',
    'power-shutdown', 'power-restart', 'power-lock', 'power-sleep',
    'power-logoff', 'power-status'];
  for (const id of ids) {
    assert.ok(html32.indexOf('id="' + id + '"') >= 0, 'missing #' + id);
  }
});

ok('v3.4 markup: manual control sections removed in v3.4 are absent', () => {
  const html34 = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  const removed = ['printer-select', 'printers-list', 'run-input', 'run-btn',
    'run-output', 'open-input', 'open-btn', 'open-status', 'shot-btn',
    'shot-status', 'shot-img', 'clip-text', 'clip-get', 'clip-set',
    'clip-status', 'vol-down', 'vol-mute', 'vol-up', 'windows-refresh',
    'windows-list', 'proc-refresh', 'proc-list'];
  for (const id of removed) {
    assert.ok(html34.indexOf('id="' + id + '"') < 0, 'should be removed: #' + id);
  }
});

ok('v3.2: taskBody coerces a numeric-string bot_id to a number', () => {
  assert.deepStrictEqual(app.taskBody('5', 't', 'p'),
    { bot_id: 5, title: 't', prompt: 'p' });
  assert.deepStrictEqual(app.taskBody('b1', 't', 'p'),
    { bot_id: 'b1', title: 't', prompt: 'p' });
  assert.strictEqual(app.coerceNumericId('7'), 7);
  assert.strictEqual(app.coerceNumericId('3.5'), '3.5');
});

ok('v3.2: parseTasks + parseTaskDetail normalize and filter', () => {
  assert.deepStrictEqual(
    app.parseTasks({ tasks: [{ id: 3, title: 'A', status: 'done' }, { title: 'x' }] }),
    [{ id: '3', bot_id: '', bot_name: '', title: 'A', status: 'done',
       created_at: '', started_at: '', finished_at: '' }]);
  throwsKind(() => app.parseTasks({ tasks: {} }), 'bad_shape');
  const d = app.parseTaskDetail({ task: { id: 1, title: 'T', prompt: 'P',
    log: [{ ts: '1', kind: 'k', text: 'line' }, 'plain'] } });
  assert.strictEqual(d.prompt, 'P');
  assert.deepStrictEqual(d.log, [{ ts: '1', kind: 'k', text: 'line' },
    { ts: '', kind: '', text: 'plain' }]);
  throwsKind(() => app.parseTaskDetail({}), 'bad_shape');
});

ok('v3.2: task status labels — six statuses, both languages, unknown fallback', () => {
  const statuses = ['queued', 'running', 'waiting_approval', 'done',
    'failed', 'cancelled'];
  assert.deepStrictEqual(app.TASK_STATUSES, statuses);
  app.setLang('ar');
  for (const s of statuses) {
    assert.strictEqual(app.taskStatusKey(s), 'task_status_' + s);
    assert.strictEqual(app.taskStatusLabel(s), app.STRINGS.ar['task_status_' + s]);
  }
  app.setLang('en');
  for (const s of statuses) {
    assert.strictEqual(app.taskStatusLabel(s), app.STRINGS.en['task_status_' + s]);
  }
  assert.strictEqual(app.taskStatusKey('nope'), 'task_status_unknown');
  assert.strictEqual(app.taskStatusLabel('nope'), app.STRINGS.en.task_status_unknown);
  app.setLang('ar');
});

ok('v3.2: parseStatus + formatUptime + formatSize', () => {
  const st = app.parseStatus({ hostname: 'PC', home: '/home/u', uptime_s: 60,
    disk: { total_gb: 100, free_gb: 40 }, ram_mb: null });
  assert.strictEqual(st.hostname, 'PC');
  assert.deepStrictEqual(st.disk, { total_gb: 100, free_gb: 40 });
  assert.strictEqual(st.ram_mb, null);
  assert.strictEqual(app.parseStatus({}).disk, null);
  throwsKind(() => app.parseStatus(null), 'bad_shape');
  assert.strictEqual(app.formatUptime(0), '0:00:00');
  assert.strictEqual(app.formatUptime(3661), '1:01:01');
  assert.strictEqual(app.formatUptime(90061), '1d 1:01:01');
  app.setLang('ar');
  assert.strictEqual(app.formatSize(2048), '2 KB');
  assert.strictEqual(app.formatSize(null), '');
});

ok('v3.2: parseFiles + joinRemotePath (traversal-free rendering inputs)', () => {
  const listing = app.parseFiles({ path: '/home/u', parent: '/home', entries: [
    { name: 'docs', kind: 'dir' }, { name: 'a.txt', kind: 'file', size: 12 },
    { name: '' }, null] });
  assert.deepStrictEqual(listing.entries, [
    { name: 'docs', kind: 'dir', size: null },
    { name: 'a.txt', kind: 'file', size: 12 }]);
  assert.strictEqual(listing.parent, '/home');
  throwsKind(() => app.parseFiles({ entries: {} }), 'bad_shape');
  assert.strictEqual(app.joinRemotePath('/home/u', 'a.txt'), '/home/u/a.txt');
  assert.strictEqual(app.joinRemotePath('C:\\Users\\u', 'a.txt'),
    'C:\\Users\\u\\a.txt');
  assert.strictEqual(app.joinRemotePath('C:\\', 'a.txt'), 'C:\\a.txt');
  assert.strictEqual(app.joinRemotePath('', 'a.txt'), 'a.txt');
});

ok('v3.2: parseFileDownload guards the base64 payload', () => {
  assert.deepStrictEqual(
    app.parseFileDownload({ name: 'a', size: 3, content_b64: 'QUJD' }),
    { name: 'a', size: 3, content_b64: 'QUJD' });
  throwsKind(() => app.parseFileDownload({ name: 'a' }), 'bad_shape');
});

ok('v3.2: run/open/power bodies and result parsers', () => {
  assert.deepStrictEqual(app.runBody('dir'), { command: 'dir' });
  assert.deepStrictEqual(app.parseRunResult({ exit: 2, stdout: 'o' }),
    { exit: 2, stdout: 'o', stderr: '', timed_out: false });
  assert.deepStrictEqual(app.openBody('notepad'), { target: 'notepad' });
  for (const a of ['shutdown', 'restart', 'lock', 'sleep', 'logoff']) {
    assert.deepStrictEqual(app.powerBody(a), { action: a });
  }
  assert.deepStrictEqual(app.powerBody('bogus'), { action: 'shutdown' });
  assert.deepStrictEqual(app.parsePower({ ok: true, scheduled_in_s: 5 }),
    { ok: true, scheduled_in_s: 5 });
  assert.deepStrictEqual(app.parsePower({ ok: true }),
    { ok: true, scheduled_in_s: null });
});

ok('v3.2: screenshot data-URI builder sanitizes the format', () => {
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

ok('v3.2: printBody omits an empty printer, parsePrinters normalizes', () => {
  const b = app.printBody('/a/b.txt', '  ');
  assert.deepStrictEqual(b, { path: '/a/b.txt' });
  assert.ok(!('printer' in b));
  assert.deepStrictEqual(app.printBody('/a/b.txt', ' HP '),
    { path: '/a/b.txt', printer: 'HP' });
  assert.deepStrictEqual(
    app.parsePrinters({ printers: [{ name: 'HP', is_default: true },
      { name: 'PDF' }, { name: '' }] }),
    [{ name: 'HP', is_default: true }, { name: 'PDF', is_default: false }]);
  throwsKind(() => app.parsePrinters({}), 'bad_shape');
});

ok('v3.2: uploadBody splits the base64 payload off a data URL', () => {
  assert.deepStrictEqual(
    app.uploadBody('a.txt', 'data:text/plain;base64,QUJD'),
    { path: 'a.txt', content_b64: 'QUJD' });
  assert.deepStrictEqual(
    app.uploadBody('a.txt', 'QUJD'), { path: 'a.txt', content_b64: 'QUJD' });
  assert.deepStrictEqual(
    app.uploadBody('a.txt', 'data:image/png;base64,QU JD\n'),
    { path: 'a.txt', content_b64: 'QUJD' });
});

ok('v3.2: clipboardBody + parseClipboard', () => {
  assert.deepStrictEqual(app.clipboardBody('x'), { text: 'x' });
  assert.deepStrictEqual(app.clipboardBody(null), { text: '' });
  assert.strictEqual(app.parseClipboard({ text: 'hello' }), 'hello');
  throwsKind(() => app.parseClipboard({}), 'bad_shape');
});

ok('v3.2: volumeBody + parseWindows + windowBody', () => {
  assert.deepStrictEqual(app.volumeBody('up'), { action: 'up' });
  assert.deepStrictEqual(app.volumeBody('bogus'), { action: 'mute' });
  assert.deepStrictEqual(
    app.parseWindows({ windows: [{ id: 5, title: 'T' }, { title: 'x' }] }),
    [{ id: 5, title: 'T' }]);
  throwsKind(() => app.parseWindows({}), 'bad_shape');
  assert.deepStrictEqual(app.windowBody('42', 'close'), { id: 42, action: 'close' });
  assert.deepStrictEqual(app.windowBody(7, 'bogus'), { id: 7, action: 'focus' });
});

ok('v3.2: parseProcesses + killBody', () => {
  assert.deepStrictEqual(
    app.parseProcesses({ processes: [{ pid: '12', name: 'b', mem_mb: 'x' },
      { pid: 3, name: 'a', mem_mb: 50 }, { pid: 'x' }] }),
    [{ pid: 12, name: 'b', mem_mb: null }, { pid: 3, name: 'a', mem_mb: 50 }]);
  throwsKind(() => app.parseProcesses({}), 'bad_shape');
  assert.deepStrictEqual(app.killBody('42'), { pid: 42 });
});

/* ================= Wake-on-LAN (phone-side helpers) ================= */

ok('wol: normalizeMac accept matrix normalizes to canonical form', () => {
  assert.strictEqual(app.normalizeMac('AA:BB:CC:DD:EE:FF'), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac('aa-bb-cc-dd-ee-ff'), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac('aabbccddeeff'), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac(' Aa:Bb:Cc:Dd:Ee:Ff '), 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizeMac('01:23:45:67:89:ab'), '01:23:45:67:89:AB');
});

ok('wol: normalizeMac reject matrix returns null', () => {
  assert.strictEqual(app.normalizeMac('AA:BB:CC:DD:EE'), null);
  assert.strictEqual(app.normalizeMac('AA:BB:CC:DD:EE:FF:00'), null);
  assert.strictEqual(app.normalizeMac('GG:BB:CC:DD:EE:FF'), null);
  assert.strictEqual(app.normalizeMac(''), null);
  assert.strictEqual(app.normalizeMac(null), null);
  assert.strictEqual(app.normalizeMac(undefined), null);
});

ok('wol: saved settings persist mac and tolerate a missing one', () => {
  __lsStore['krouchi.pc.v1'] = JSON.stringify({ host: 'old', port: 8765, token: 'x' });
  const old = app.loadPcConfig();
  assert.strictEqual(old.host, 'old');
  assert.strictEqual(old.mac, '');
  const saved = app.savePcConfig({ host: 'h', token: 't', mac: 'aa-bb-cc-dd-ee-ff' });
  assert.strictEqual(saved.mac, 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.loadPcConfig().mac, 'AA:BB:CC:DD:EE:FF');
  assert.strictEqual(app.normalizePcConfig({ mac: 'bogus' }).mac, '');
});

ok('wol markup: pcMac field and pcWakeBtn exist in index.html', () => {
  const h = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  assert.ok(h.indexOf('id="pcMac"') >= 0, 'missing #pcMac');
  assert.ok(h.indexOf('id="pcWakeBtn"') >= 0, 'missing #pcWakeBtn');
});

/* ================= v3.3: live screen helpers ================= */

ok('screen: screenStreamUrl shape, defaults and token encoding', () => {
  assert.strictEqual(
    app.screenStreamUrl({ host: '192.168.1.10', token: 'tok123' }, { w: 1280, q: 60, fps: 10 }),
    'http://192.168.1.10:8765/api/screen/stream?token=tok123&w=1280&q=60&fps=10');
  assert.strictEqual(
    app.screenStreamUrl({ host: 'pc.local', port: 9000, token: 'a b&c=d' }, { w: 960, q: 40, fps: 5 }),
    'http://pc.local:9000/api/screen/stream?token=a%20b%26c%3Dd&w=960&q=40&fps=5');
  assert.strictEqual(
    app.screenStreamUrl({ host: '192.168.1.10', token: 't' }),
    'http://192.168.1.10:8765/api/screen/stream?token=t&w=1280&q=60&fps=10');
});

ok('screen: screenFramePath shape and defaults (v3.3.2)', () => {
  assert.strictEqual(
    app.screenFramePath({ w: 1280, q: 60 }),
    '/api/screen/frame?w=1280&q=60');
  assert.strictEqual(app.screenFramePath(), '/api/screen/frame?w=1280&q=60');
  assert.strictEqual(
    app.screenFramePath({ w: 640, q: 45 }),
    '/api/screen/frame?w=640&q=45');
});

ok('screen: normPoint corners, center and clamping', () => {
  const rect = { left: 100, top: 50, width: 400, height: 200 };
  assert.deepStrictEqual(app.normPoint(100, 50, rect), { x: 0, y: 0 });
  assert.deepStrictEqual(app.normPoint(500, 250, rect), { x: 1, y: 1 });
  assert.deepStrictEqual(app.normPoint(300, 150, rect), { x: 0.5, y: 0.5 });
  assert.deepStrictEqual(app.normPoint(-5, 999, rect), { x: 0, y: 1 });
  assert.deepStrictEqual(app.normPoint(10, 10, { left: 0, top: 0, width: 0, height: 0 }), { x: 0, y: 0 });
  assert.deepStrictEqual(app.normPoint(10, 10, null), { x: 0, y: 0 });
});

ok('screen: input body builders (mouse, wheel, key, text)', () => {
  assert.deepStrictEqual(app.inputMouseBody('mouse_down', { x: 0.5, y: 0.25 }),
    { type: 'mouse_down', x: 0.5, y: 0.25, button: 'left' });
  assert.deepStrictEqual(app.inputMouseBody('mouse_up', { x: 0, y: 1 }, 'right'),
    { type: 'mouse_up', x: 0, y: 1, button: 'right' });
  assert.deepStrictEqual(app.inputMouseBody('bogus', { x: 2, y: -1 }),
    { type: 'mouse_move', x: 1, y: 0, button: 'left' });
  assert.deepStrictEqual(app.inputWheelBody({ x: 0.5, y: 0.5 }, 1),
    { type: 'wheel', x: 0.5, y: 0.5, delta: 1 });
  assert.deepStrictEqual(app.inputWheelBody({ x: 0.5, y: 0.5 }, -1),
    { type: 'wheel', x: 0.5, y: 0.5, delta: -1 });
  assert.deepStrictEqual(app.inputKeyBody('alt+tab'), { type: 'key', key: 'alt+tab' });
  assert.deepStrictEqual(app.inputKeyBody(null), { type: 'key', key: '' });
  assert.deepStrictEqual(app.inputTextBody('hi'), { type: 'text', text: 'hi' });
  assert.deepStrictEqual(app.inputTextBody(null), { type: 'text', text: '' });
});

ok('screen markup: live screen section and keys exist in index.html', () => {
  const hs = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  const ids = ['pc-screen-wrap', 'screen-start', 'screen-stop', 'screen-drag',
    'screen-status', 'pcScreenImg', 'screen-wheel-up', 'screen-wheel-down',
    'screen-text', 'screen-send-text'];
  for (const id of ids) {
    assert.ok(hs.indexOf('id="' + id + '"') >= 0, 'missing #' + id);
  }
  const keys = ['enter', 'esc', 'tab', 'backspace', 'delete', 'up', 'down',
    'left', 'right', 'ctrl+c', 'ctrl+v', 'ctrl+z', 'alt+tab', 'win'];
  for (const k of keys) {
    assert.ok(hs.indexOf('data-screen-key="' + k + '"') >= 0, 'missing key ' + k);
  }
});

/* ================= v3.4: multi-computer registry ================= */

function clearPcKeysPwa() {
  delete __lsStore['krouchi.pcs.v1'];
  delete __lsStore['krouchi.pcs.active.v1'];
  delete __lsStore['krouchi.pc.v1'];
}

ok('v3.4 registry: legacy-only storage migrates to one active entry', () => {
  clearPcKeysPwa();
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

ok('v3.4 registry: add, switch and delete entries', () => {
  clearPcKeysPwa();
  const a = app.addPcEntry({ name: 'Alpha', host: '10.0.0.1', token: 'ta' });
  const b = app.addPcEntry({ name: 'Beta', host: '10.0.0.2', token: 'tb' });
  assert.strictEqual(app.loadPcRegistry().length, 2);
  assert.strictEqual(app.getActivePcEntry().id, b.id);
  assert.strictEqual(app.setActivePcEntry(a.id).name, 'Alpha');
  assert.strictEqual(app.loadPcConfig().host, '10.0.0.1');
  assert.strictEqual(app.removePcEntry(a.id).id, b.id);
  assert.strictEqual(app.removePcEntry(b.id), null);
  assert.deepStrictEqual(app.loadPcRegistry(), []);
});

ok('v3.4 registry: resolvePcEntry default, by name, unknown lists names', () => {
  const reg = [
    { id: 'p1', name: 'Home PC', host: 'h1', port: 8765, token: 't', mac: '' },
    { id: 'p2', name: 'Office', host: 'h2', port: 8765, token: 't', mac: '' }];
  assert.strictEqual(app.resolvePcEntry('', reg, 'p2').entry.name, 'Office');
  assert.strictEqual(app.resolvePcEntry('home pc', reg, 'p2').entry.id, 'p1');
  const miss = app.resolvePcEntry('Nope', reg, 'p1');
  assert.strictEqual(miss.entry, null);
  assert.ok(miss.error.indexOf('computer not found: Nope') === 0);
  assert.ok(miss.error.indexOf('Office') >= 0);
});

ok('v3.4 registry markup: selector, name field and add/delete buttons', () => {
  const h = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  for (const id of ['pc-select', 'pc-add', 'pc-delete', 'pc-name']) {
    assert.ok(h.indexOf('id="' + id + '"') >= 0, 'missing #' + id);
  }
});

/* ================= v3.4: delegation tools + reports ================= */

ok('v3.4 delegation: tool definitions (names, required params)', () => {
  const byName = {};
  for (const tool of app.PC_DELEGATION_TOOLS) byName[tool.function.name] = tool;
  assert.deepStrictEqual(Object.keys(byName).sort(),
    ['pc_ask', 'pc_bots', 'pc_report', 'pc_task']);
  assert.deepStrictEqual(byName.pc_ask.function.parameters.required, ['bot', 'message']);
  assert.deepStrictEqual(byName.pc_task.function.parameters.required, ['bot', 'task']);
  assert.deepStrictEqual(byName.pc_bots.function.parameters.required, []);
  assert.deepStrictEqual(byName.pc_report.function.parameters.required, []);
});

ok('v3.4 delegation: providerKind detects Gemini, defaults to openai', () => {
  assert.strictEqual(app.providerKind({ kind: 'gemini', base: 'https://x' }), 'gemini');
  assert.strictEqual(app.providerKind({ base: 'https://generativelanguage.googleapis.com/v1beta' }), 'gemini');
  assert.strictEqual(app.providerKind({ base: 'https://openrouter.ai/api/v1' }), 'openai');
});

ok('v3.4 report: formatPcReport contains counts and names', () => {
  const status = app.parseStatus({ app: 'Krouchi_DZ', version: '3.4.0',
    hostname: 'DESKTOP-1', uptime_s: 3661, disk: null, ram_mb: null });
  const tasks = app.parseTasks({ tasks: [
    { id: 3, bot_name: 'Helper', title: 'Latest job', status: 'done' },
    { id: 2, bot_name: 'Helper', title: 'Working', status: 'running' },
    { id: 1, bot_name: 'Writer', title: 'Old', status: 'done' }] });
  const text = app.formatPcReport(status, tasks, 'Home PC');
  assert.ok(text.indexOf('Home PC') >= 0);
  assert.ok(text.indexOf('3.4.0') >= 0);
  assert.ok(text.indexOf('done: 2') >= 0);
  assert.ok(text.indexOf('running: 1') >= 0);
  assert.ok(text.indexOf('Helper [done] Latest job') >= 0);
  assert.ok(text.indexOf('Writer') >= 0);
});

function fakePcTransportPwa(script) {
  const state = { taskGets: 0 };
  return function (method, url, headers, body) {
    const path = url.replace(/^http:\/\/[^/]+/, '');
    const reply = (obj) => Promise.resolve(
      { status: 200, text: JSON.stringify(obj), error: '' });
    if (path === '/api/bots') {
      return reply({ bots: [{ id: 7, name: 'Helper', provider: 'p', model: 'm-x', mode: 'ask' }] });
    }
    if (path === '/api/tasks' && method === 'POST') {
      return reply({ task: { id: 5, bot_id: 7, title: 'x', status: 'queued', created_at: 'c' } });
    }
    if (path === '/api/tasks/5') {
      state.taskGets++;
      const step = script[Math.min(state.taskGets - 1, script.length - 1)];
      return reply({ task: Object.assign(
        { id: 5, bot_id: 7, bot_name: 'Helper', title: 'x' }, step) });
    }
    return Promise.resolve({ status: 404, text: '{"error":"x"}', error: '' });
  };
}
const REG1_PWA = [{ id: 'pc1', name: 'Home PC', host: '192.168.1.10',
  port: 8765, token: 'tok', mac: '' }];

(async () => {
  await okAsync('v3.4 delegation: pc_task polls created -> running -> done', async () => {
    const transport = fakePcTransportPwa([
      { status: 'running' },
      { status: 'done', result: 'final result text' }]);
    const out = await app.executePcTool('pc_task',
      { bot: 'Helper', task: 'do it' },
      { registry: REG1_PWA, activeId: 'pc1', transport,
        pollIntervalMs: 1, maxPollMs: 1000, sleep: () => Promise.resolve() });
    assert.ok(out.indexOf('Task 5 done.') === 0, out);
    assert.ok(out.indexOf('final result text') >= 0);
  });
  await okAsync('v3.4 delegation: pc_task still-running note at the cap', async () => {
    const transport = fakePcTransportPwa([{ status: 'running' }]);
    const out = await app.executePcTool('pc_task',
      { bot: 'Helper', task: 'long job' },
      { registry: REG1_PWA, activeId: 'pc1', transport,
        pollIntervalMs: 10, maxPollMs: 30, sleep: () => Promise.resolve() });
    assert.ok(out.indexOf('still running') >= 0, out);
  });
  await okAsync('v3.4 delegation: chat loop executes tool_calls then final text', async () => {
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
        choices: [{ message: { content: 'final answer' } }] }) });
    };
    const reply = await app.sendChatWithTools('https://api.example.com/v1',
      'sk', 'm', [{ role: 'user', content: 'list pc bots' }], {
        tools: app.PC_DELEGATION_TOOLS, transport,
        executeTool: () => Promise.resolve('Helper — m-x')
      });
    assert.strictEqual(reply, 'final answer');
    assert.ok(Array.isArray(bodies[0].tools));
    const toolMsg = bodies[1].messages[bodies[1].messages.length - 1];
    assert.strictEqual(toolMsg.role, 'tool');
    assert.strictEqual(toolMsg.tool_call_id, 'c1');
  });
})();

/* ================= v3.4: keyboard layouts + screen markup ================= */

ok('v3.4 keyboard: KB_LAYOUTS sanity (3 layouts, valid acts, F-row, arrows)', () => {
  assert.deepStrictEqual(Object.keys(app.KB_LAYOUTS).sort(), ['ar', 'azerty', 'en']);
  const kinds = ['text', 'key', 'mod', 'space'];
  for (const name of Object.keys(app.KB_LAYOUTS)) {
    const rows = app.KB_LAYOUTS[name].rows;
    assert.strictEqual(rows[0].length, 12, name + ': F-row has 12');
    rows[0].forEach((key, i) => {
      assert.deepStrictEqual(key.act, { t: 'key', v: 'f' + (i + 1) });
    });
    const acts = [];
    for (const row of rows) {
      for (const key of row) {
        assert.ok(typeof key.label === 'string' && key.label.length > 0);
        assert.ok(key.act && kinds.indexOf(key.act.t) >= 0);
        if (key.act.t !== 'space') {
          assert.ok(typeof key.act.v === 'string' && key.act.v.length > 0);
        }
        acts.push(key.act);
      }
    }
    for (const arrow of ['left', 'up', 'down', 'right']) {
      assert.ok(acts.some((a) => a.t === 'key' && a.v === arrow), name + ': ' + arrow);
    }
    assert.ok(acts.some((a) => a.t === 'space'), name + ': space');
    assert.deepStrictEqual(app.inputComboBody(['ctrl', 'c']),
      { type: 'combo', keys: ['ctrl', 'c'] });
  }
});

ok('v3.4 screen markup: fullscreen toggle, keyboard container, reports section', () => {
  const h = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  for (const id of ['screen-fullscreen', 'screen-kb', 'screen-kb-layout',
      'report-status', 'report-counts', 'report-tasks', 'report-refresh']) {
    assert.ok(h.indexOf('id="' + id + '"') >= 0, 'missing #' + id);
  }
  assert.ok(h.indexOf('.screen-full') >= 0, 'screen-full CSS class defined');
});

ok('v3.4 version: 3.4.0 in app.js + index.html, sw.js cache v5', () => {
  const js = fs.readFileSync(path.join(DIR, 'app.js'), 'utf8');
  const h = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  const sw = fs.readFileSync(path.join(DIR, 'sw.js'), 'utf8');
  assert.ok(js.indexOf('3.4.0') >= 0, 'app.js');
  assert.ok(h.indexOf('3.4.0') >= 0, 'index.html');
  assert.ok(app.STRINGS.ar.about_p1.indexOf('3.4.0') >= 0);
  assert.ok(app.STRINGS.en.about_p1.indexOf('3.4.0') >= 0);
  assert.ok(sw.indexOf('krouchi-dz-shell-v5') >= 0, 'sw cache v5');
});

/* ================= bot avatars (v3.4) ================= */

ok('avatars: AVATAR_GALLERY is exactly the six gallery names', () => {
  assert.deepStrictEqual(app.AVATAR_GALLERY,
    ['bot_1.png', 'bot_2.png', 'bot_3.png', 'bot_4.png', 'bot_5.png', 'bot_6.png']);
});

ok('avatars: normalizeBotAvatar keeps gallery names only', () => {
  assert.strictEqual(app.normalizeBotAvatar('bot_6.png'), 'bot_6.png');
  assert.strictEqual(app.normalizeBotAvatar(''), '');
  assert.strictEqual(app.normalizeBotAvatar('evil.png'), '');
  assert.strictEqual(app.normalizeBotAvatar('🤖'), '');
  assert.strictEqual(app.normalizeBotAvatar(7), '');
  assert.strictEqual(app.normalizeBotAvatar(null), '');
});

ok('avatars: legacy bot without avatar normalizes to empty string', () => {
  assert.deepStrictEqual(
    app.normalizeBot({ id: 'b1', name: 'Old', providerId: 'p', model: 'm' }),
    { id: 'b1', name: 'Old', providerId: 'p', model: 'm', avatar: '' });
  __lsStore['krouchi.bots.v1'] = JSON.stringify([
    { id: 'b1', name: 'Old', providerId: 'p', model: 'm' },
    { id: 'b2', name: 'New', providerId: 'p', model: 'm', avatar: 'bot_1.png' },
    { id: 'b3', name: 'Bad', providerId: 'p', model: 'm', avatar: 'x.png' }]);
  assert.deepStrictEqual(app.loadBots().map((b) => b.avatar),
    ['', 'bot_1.png', '']);
  delete __lsStore['krouchi.bots.v1'];
});

ok('avatars: botAvatarHtml gallery -> img with right src + onerror + monogram underlay', () => {
  const htmlA = app.botAvatarHtml({ name: 'Helper', avatar: 'bot_3.png' });
  assert.ok(htmlA.indexOf('<img class="bot-avatar') >= 0, htmlA);
  assert.ok(htmlA.indexOf('src="avatars/bot_3.png"') >= 0, htmlA);
  assert.ok(htmlA.indexOf('onerror=') >= 0, htmlA);
  assert.ok(htmlA.indexOf('bot-avatar-mono') >= 0, htmlA);
});

ok('avatars: botAvatarHtml empty/unknown/emoji -> monogram with correct letter', () => {
  const en = app.botAvatarHtml({ name: 'helper', avatar: '' });
  assert.ok(en.indexOf('bot-avatar-mono') >= 0 && en.indexOf('>H<') >= 0, en);
  assert.ok(en.indexOf('<img') < 0, en);
  const ar = app.botAvatarHtml({ name: 'مساعد', avatar: '' });
  assert.ok(ar.indexOf('>م<') >= 0, ar);
  for (const bad of ['bot_99.png', '🤖']) {
    const h = app.botAvatarHtml({ name: 'Bot', avatar: bad });
    assert.ok(h.indexOf('<img') < 0 && h.indexOf('>B<') >= 0, bad);
  }
});

ok('avatars: parsePcBots passes avatar through with empty default', () => {
  assert.deepStrictEqual(
    app.parsePcBots({ bots: [
      { id: 1, name: 'A', avatar: 'bot_2.png' },
      { id: 2, name: 'B', avatar: 'old.png' },
      { id: 3, name: 'C' }] }).map((b) => b.avatar),
    ['bot_2.png', '', '']);
});

ok('avatars: picker markup in index.html + avatarPickerHtml tiles and selection', () => {
  const h = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  assert.ok(h.indexOf('id="bot-avatar-picker"') >= 0, 'picker container');
  assert.ok(h.indexOf('data-i18n="avatar_label"') >= 0, 'picker label');
  assert.ok(h.indexOf('id="chat-bot-header"') >= 0, 'local chat header');
  assert.ok(h.indexOf('id="pc-chat-bot-header"') >= 0, 'pc chat header');
  app.setLang('ar');
  const tiles = app.avatarPickerHtml('bot_2.png', 'مساعد');
  for (const f of app.AVATAR_GALLERY) {
    assert.ok(tiles.indexOf('data-avatar="' + f + '"') >= 0, f);
    assert.ok(tiles.indexOf('src="avatars/' + f + '"') >= 0, f);
  }
  assert.ok(tiles.indexOf('data-avatar=""') >= 0, 'none tile');
  assert.ok(tiles.indexOf(app.STRINGS.ar.avatar_none) >= 0, 'none label');
  assert.ok(tiles.indexOf('avatar-tile selected" data-avatar="bot_2.png"') >= 0,
    'selected tile');
});

ok('avatars: CSS animation keyframes + reduced-motion in index.html', () => {
  const h = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  assert.ok(/@keyframes avatar-bob/.test(h), 'avatar-bob keyframes');
  assert.ok(/@keyframes avatar-bounce/.test(h), 'avatar-bounce keyframes');
  assert.ok(h.indexOf('prefers-reduced-motion') >= 0, 'reduced-motion guard');
  assert.ok(h.indexOf('avatar-bob 3.2s') >= 0, 'bob applied to header avatar');
});

ok('avatars: sw.js caches all six gallery files, CACHE_NAME still v5', () => {
  const sw = fs.readFileSync(path.join(DIR, 'sw.js'), 'utf8');
  for (const f of app.AVATAR_GALLERY) {
    assert.ok(sw.indexOf("'./avatars/" + f + "'") >= 0, 'sw missing ' + f);
  }
  assert.ok(sw.indexOf("var CACHE_NAME = 'krouchi-dz-shell-v5';") >= 0,
    'cache name unchanged');
});

ok('avatars: gallery files exist in the pwa folder', () => {
  for (const f of app.AVATAR_GALLERY) {
    assert.ok(fs.existsSync(path.join(DIR, 'avatars', f)), 'missing avatars/' + f);
  }
});

/* ================= v3.4: shared API + role prompt + mandatory delegation loop ================= */

let passedSharedPwa = 0;
function okSh(name, fn) {
  try { fn(); passedSharedPwa++; console.log('PASS ' + name); }
  catch (e) { console.error('FAIL ' + name + ': ' + e.message); process.exitCode = 1; }
}
async function okShAsync(name, fn) {
  try { await fn(); passedSharedPwa++; console.log('PASS ' + name); }
  catch (e) { console.error('FAIL ' + name + ': ' + e.message); process.exitCode = 1; }
}
function clearSharedKeysPwa() {
  delete __lsStore[app.LS_SHARED_API];
  delete __lsStore[app.LS_PROVIDERS];
  delete __lsStore[app.LS_BOTS];
  delete __lsStore[app.LS_CHATS];
}

app.setLang('ar');

okSh('shared API: storage round-trip under krouchi.sharedApi.v1', () => {
  clearSharedKeysPwa();
  assert.strictEqual(app.LS_SHARED_API, 'krouchi.sharedApi.v1');
  assert.deepStrictEqual(app.saveSharedApi({ providerId: 'p1', model: 'm-x' }),
    { providerId: 'p1', model: 'm-x' });
  assert.deepStrictEqual(JSON.parse(__lsStore['krouchi.sharedApi.v1']),
    { providerId: 'p1', model: 'm-x' });
  assert.deepStrictEqual(app.loadSharedApi(), { providerId: 'p1', model: 'm-x' });
  delete __lsStore[app.LS_SHARED_API];
  assert.strictEqual(app.loadSharedApi(), null);
});

okSh('shared API migration: keyed provider preferred, model from most recent used bot', () => {
  clearSharedKeysPwa();
  app.saveProviders([
    { id: 'p1', name: 'nokey', base: 'https://a.example/v1', key: '', models: ['a1'] },
    { id: 'p2', name: 'keyed', base: 'https://b.example/v1', key: 'sk-2', models: ['b1', 'b2'] }]);
  app.saveBots([
    { id: 'bold', name: 'Old', providerId: 'p2', model: 'model-old', system: '' },
    { id: 'bnew', name: 'New', providerId: 'p2', model: 'model-new', system: '' },
    { id: 'bother', name: 'Other', providerId: 'p1', model: 'a1', system: '' }]);
  app.saveChats({
    bold: [{ role: 'user', content: 'q' }],
    bnew: [{ role: 'user', content: 'q' }, { role: 'assistant', content: 'a' }] });
  assert.deepStrictEqual(app.migrateSharedApi(),
    { providerId: 'p2', model: 'model-new' });
  assert.deepStrictEqual(app.loadSharedApi(),
    { providerId: 'p2', model: 'model-new' });
});

okSh('shared API migration: no chat history -> first bound bot model', () => {
  clearSharedKeysPwa();
  app.saveProviders([
    { id: 'p1', name: 'one', base: 'https://a.example/v1', key: 'sk', models: ['m1', 'm2'] }]);
  app.saveBots([
    { id: 'b1', name: 'First', providerId: 'p1', model: 'm-first', system: '' },
    { id: 'b2', name: 'Second', providerId: 'p1', model: 'm-second', system: '' }]);
  app.saveChats({});
  assert.deepStrictEqual(app.migrateSharedApi(),
    { providerId: 'p1', model: 'm-first' });
});

okSh('shared API migration: no keys -> first provider, unbound -> empty model', () => {
  clearSharedKeysPwa();
  app.saveProviders([
    { id: 'p1', name: 'one', base: 'https://a.example/v1', key: '', models: ['m1'] },
    { id: 'p2', name: 'two', base: 'https://b.example/v1', key: '', models: ['m2'] }]);
  app.saveBots([]);
  assert.deepStrictEqual(app.migrateSharedApi(), { providerId: 'p1', model: '' });
});

okSh('shared API migration: no providers -> stays unset, nothing written', () => {
  clearSharedKeysPwa();
  app.saveProviders([]);
  assert.strictEqual(app.migrateSharedApi(), null);
  assert.strictEqual(app.loadSharedApi(), null);
  assert.ok(!(app.LS_SHARED_API in __lsStore));
});

okSh('shared API migration: an existing shared API is never overwritten', () => {
  clearSharedKeysPwa();
  app.saveProviders([
    { id: 'p9', name: 'x', base: 'https://x.example/v1', key: 'sk', models: ['mx'] }]);
  app.saveSharedApi({ providerId: 'keep', model: 'keep-model' });
  assert.deepStrictEqual(app.migrateSharedApi(),
    { providerId: 'keep', model: 'keep-model' });
});

okSh('role prompt: constants carry the tool names and the never-claim phrase', () => {
  for (const tool of ['pc_bots', 'pc_ask', 'pc_task', 'pc_report']) {
    assert.ok(app.ROLE_PROMPT_AR.indexOf(tool) >= 0, 'ar: ' + tool);
    assert.ok(app.ROLE_PROMPT_EN.indexOf(tool) >= 0, 'en: ' + tool);
  }
  assert.ok(app.ROLE_PROMPT_AR.indexOf('لا تستطيع التواصل مع بوتات الحاسوب') >= 0);
  assert.ok(app.ROLE_PROMPT_EN.indexOf(
    'never say you cannot communicate with the computer bots') >= 0);
  assert.strictEqual(app.getRolePrompt('ar'), app.ROLE_PROMPT_AR);
  assert.strictEqual(app.getRolePrompt('en'), app.ROLE_PROMPT_EN);
});

okSh('role prompt: composed system = role first, then the bot prompt', () => {
  assert.strictEqual(app.composeSystemContent({ system: 'My own rules' }),
    app.ROLE_PROMPT_AR + '\n\n' + 'My own rules');
  assert.strictEqual(app.composeSystemContent({ system: '' }), app.ROLE_PROMPT_AR);
  assert.strictEqual(app.composeSystemContent({ system: 'Mine' }, 'en'),
    app.ROLE_PROMPT_EN + '\n\n' + 'Mine');
  const convo = app.buildLocalConvo({ system: 'S' }, [{ role: 'user', content: 'hi' }]);
  assert.strictEqual(convo[0].role, 'system');
  assert.strictEqual(convo[0].content, app.ROLE_PROMPT_AR + '\n\n' + 'S');
  assert.deepStrictEqual(convo[1], { role: 'user', content: 'hi' });
});

okSh('shared API markup: bot form pickers gone, shared line + APIs section present', () => {
  const h = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  assert.ok(h.indexOf('id="bot-provider"') < 0, 'bot-provider removed');
  assert.ok(h.indexOf('id="bot-model"') < 0, 'bot-model removed');
  assert.ok(h.indexOf('id="bot-models"') < 0, 'bot-models removed');
  assert.ok(h.indexOf('id="bot-shared-line"') >= 0, 'shared line');
  assert.ok(h.indexOf('id="bot-shared-change"') >= 0, 'shared change button');
  assert.ok(h.indexOf('id="shared-provider"') >= 0, 'shared provider select');
  assert.ok(h.indexOf('id="shared-model"') >= 0, 'shared model select');
  assert.ok(h.indexOf('id="shared-save"') >= 0, 'shared save button');
});

(async () => {
  await okShAsync('shared resolution: a bot stale binding is ignored at send time', async () => {
    clearSharedKeysPwa();
    app.setLang('ar');
    app.saveProviders([
      { id: 'pStale', name: 'stale', base: 'https://stale.example/v1', key: 'sk-stale', models: ['stale-model'] },
      { id: 'pShared', name: 'sharedprov', base: 'https://shared.example/v1', key: 'sk-shared', models: ['shared-model'] }]);
    app.saveSharedApi({ providerId: 'pShared', model: 'shared-model' });
    const bot = { id: 'b1', name: 'Deputy', providerId: 'pStale',
      model: 'stale-model', system: 'Bot own prompt' };
    const seen = {};
    const transport = (method, url, headers, body) => {
      Object.assign(seen, { method, url, headers, body: JSON.parse(body) });
      return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
        choices: [{ message: { content: 'shared reply' } }] }) });
    };
    const reply = await app.sendLocalBotChat(bot,
      [{ role: 'user', content: 'hello' }], { transport, registry: [] });
    assert.strictEqual(reply, 'shared reply');
    assert.strictEqual(seen.url, 'https://shared.example/v1/chat/completions');
    assert.strictEqual(seen.headers.Authorization, 'Bearer sk-shared');
    assert.strictEqual(seen.body.model, 'shared-model');
    assert.strictEqual(seen.body.messages[0].role, 'system');
    assert.strictEqual(seen.body.messages[0].content,
      app.ROLE_PROMPT_AR + '\n\n' + 'Bot own prompt');
    assert.deepStrictEqual(seen.body.messages[1], { role: 'user', content: 'hello' });
  });

  await okShAsync('shared resolution: no shared API -> err_shared_api, no provider call', async () => {
    clearSharedKeysPwa();
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
    assert.ok(err, 'expected a rejection');
    assert.strictEqual(err.kind, 'shared_api');
    assert.strictEqual(err.message, app.t('err_shared_api'));
    assert.strictEqual(calls, 0);
  });

  await okShAsync('shared resolution: deleted provider or empty model -> rejection, no call', async () => {
    clearSharedKeysPwa();
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
    clearSharedKeysPwa();
    app.setLang('ar');
    app.saveProviders([
      { id: 'pShared', name: 'sharedprov', base: 'https://shared.example/v1',
        key: 'sk-shared', models: ['shared-model'] }]);
    app.saveSharedApi({ providerId: 'pShared', model: 'shared-model' });
    const registry = [{ id: 'pc1', name: 'Home PC', host: '192.168.1.10',
      port: 8765, token: 'tok', mac: '' }];
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
          status: 'done', result: 'task result from the computer' } });
      }
      return Promise.resolve({ status: 404, text: '{"error":"x"}', error: '' });
    };
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
                arguments: '{"bot":"Helper","task":"Summarize the notes file"}' } }] } }] }) });
      }
      return Promise.resolve({ status: 200, error: '', text: JSON.stringify({
        choices: [{ message: { content: 'The computer bot finished the task' } }] }) });
    };
    const bot = { id: 'b1', name: 'Deputy', providerId: 'pStale', model: 'stale', system: '' };
    const reply = await app.sendLocalBotChat(bot,
      [{ role: 'user', content: 'Give my computer a task' }],
      { transport: providerTransport, pcTransport, registry, activeId: 'pc1' });
    /* (a) the PC transport received the task creation for the right bot */
    assert.ok(creation, 'a task was created on the computer');
    assert.strictEqual(creation.url, 'http://192.168.1.10:8765/api/tasks');
    assert.strictEqual(creation.body.bot_id, 7);
    assert.ok(creation.body.prompt.indexOf('Summarize the notes file') >= 0);
    assert.strictEqual(urls[0], 'https://shared.example/v1/chat/completions');
    assert.strictEqual(bodies[0].model, 'shared-model');
    assert.ok(Array.isArray(bodies[0].tools));
    assert.strictEqual(bodies[0].messages[0].content, app.ROLE_PROMPT_AR);
    /* (b) the second provider request carries the tool result */
    const toolMsgs = bodies[1].messages.filter((m) => m.role === 'tool');
    assert.strictEqual(toolMsgs.length, 1);
    assert.strictEqual(toolMsgs[0].tool_call_id, 'tc1');
    assert.ok(toolMsgs[0].content.indexOf('Task 5 done.') === 0, toolMsgs[0].content);
    assert.ok(toolMsgs[0].content.indexOf('task result from the computer') >= 0);
    /* (c) the final answer comes from the follow-up response */
    assert.strictEqual(reply, 'The computer bot finished the task');
  });

  await okShAsync('delegation gating: gemini shared provider -> plain send, no tools', async () => {
    clearSharedKeysPwa();
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
        choices: [{ message: { content: 'plain reply' } }] }) });
    };
    const reply = await app.sendLocalBotChat({ id: 'b1', name: 'x', system: '' },
      [{ role: 'user', content: 'hi' }], { transport, registry, activeId: 'pc1' });
    assert.strictEqual(reply, 'plain reply');
    assert.strictEqual(bodies.length, 1);
    assert.ok(!('tools' in bodies[0]), 'no tools for gemini');
    assert.strictEqual(bodies[0].messages[0].content, app.ROLE_PROMPT_AR);
  });

  clearSharedKeysPwa();
  app.setLang('ar');
  console.log('\n' + passedSharedPwa + ' shared-API tests passed (pwa)');
})();
