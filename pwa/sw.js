/* Krouchi_DZ — service worker (original code).
 *
 * Cache-first for the app shell only, so the app opens offline
 * after the first load. Everything else — provider API calls and
 * the desktop companion server — always goes to the network and
 * is never cached.
 */
'use strict';

var CACHE_NAME = 'krouchi-dz-shell-v3';
var SHELL_ASSETS = [
  './',
  './index.html',
  './app.js',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './maskable-512.png',
  './apple-touch-icon.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(SHELL_ASSETS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.map(function (name) {
        return name === CACHE_NAME ? null : caches.delete(name);
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

function isShellRequest(url) {
  var path = url.pathname;
  return SHELL_ASSETS.some(function (asset) {
    var clean = asset.replace(/^\.\//, '');
    return clean === '' ? path.endsWith('/')
      : path.endsWith('/' + clean) || path.endsWith(clean);
  });
}

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;
  var url = new URL(request.url);
  /* Cross-origin traffic (model providers, the PC companion
   * server) is never intercepted or cached. */
  if (url.origin !== self.location.origin) return;
  if (!isShellRequest(url) && request.mode !== 'navigate') return;

  event.respondWith(
    caches.match(request, { ignoreSearch: true }).then(function (hit) {
      if (hit) return hit;
      return fetch(request).then(function (response) {
        if (response && response.ok && isShellRequest(url)) {
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(request, copy);
          });
        }
        return response;
      }).catch(function () {
        if (request.mode === 'navigate') {
          return caches.match('./index.html', { ignoreSearch: true });
        }
        throw new Error('offline and not cached');
      });
    })
  );
});
