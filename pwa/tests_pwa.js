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

ok('v3.2 markup: tasks and control sections exist in index.html', () => {
  const html32 = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
  const ids = ['pc-tasks-wrap', 'task-bot', 'task-title', 'task-prompt',
    'task-create', 'task-status', 'pc-tasks-list', 'pc-task-detail',
    'task-detail-title', 'task-cancel', 'task-back', 'pc-control-wrap',
    'pc-status-fields', 'status-refresh', 'files-path', 'files-up',
    'files-list', 'files-status', 'upload-input', 'upload-status',
    'printer-select', 'printers-list', 'run-input', 'run-btn', 'run-output',
    'open-input', 'open-btn', 'shot-btn', 'shot-status', 'shot-img',
    'clip-text', 'clip-get', 'clip-set', 'vol-down', 'vol-mute', 'vol-up',
    'windows-refresh', 'windows-list', 'proc-refresh', 'proc-list',
    'power-shutdown', 'power-restart', 'power-lock', 'power-sleep',
    'power-logoff', 'power-status'];
  for (const id of ids) {
    assert.ok(html32.indexOf('id="' + id + '"') >= 0, 'missing #' + id);
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
