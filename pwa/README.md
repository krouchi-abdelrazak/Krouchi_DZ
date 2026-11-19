# Krouchi_DZ — PWA (iPhone / browser version)

This folder contains a Progressive Web App build of the Krouchi_DZ phone
app: the same bilingual (Arabic / English) interface as the Android app,
running entirely in a web browser. It is original code, written from
scratch, and it works with the user's own API keys.

By Krouchi Abderrazak.

## What is in here

| File | Purpose |
| --- | --- |
| `index.html` | The app UI (identical screens to the Android app) plus the PWA head tags and service worker registration. |
| `app.js` | All app logic: provider discovery, chat, local storage, and the desktop companion mode. |
| `manifest.webmanifest` | Web app manifest (name, colors, icons, standalone display). |
| `sw.js` | Service worker: cache-first for the app shell only, so the app opens offline after the first load. Provider API calls are never cached. |
| `icon-192.png`, `icon-512.png`, `maskable-512.png`, `apple-touch-icon.png` | App icons generated from the KA monogram. |
| `tests_pwa.js` | Node unit tests (transport, manifest, service worker, regressions). Run with `node tests_pwa.js`. |

## How it talks to providers

In the Android app, HTTP goes through a small native bridge. In the
browser there is no bridge, so the same code uses a `fetch()`-based
transport with the identical result contract and the identical request
shapes:

- Model discovery: `GET {base}/models` with an `Authorization: Bearer <key>` header.
- Chat: `POST {base}/chat/completions` with a JSON body of
  `{ "model": ..., "messages": [...] }` (OpenAI-compatible shape).
- The desktop companion mode talks HTTP to the Krouchi_DZ desktop
  server exactly as the Android app does.

API keys and conversations stay in the browser's local storage on the
device and are sent only to the provider the user chooses.

## Publishing (GitHub Pages)

The PWA is plain static files — no build step.

1. Put the contents of this `pwa/` folder at the root of the branch or
   folder that GitHub Pages serves (for example, publish the repository
   with Pages set to the `main` branch and copy these files into a
   `docs/` folder, or copy them to a dedicated `gh-pages` branch root).
2. In the repository: **Settings → Pages → Build and deployment →
   Deploy from a branch**, pick that branch/folder, and save.
3. Wait for the Pages URL (`https://<user>.github.io/<repo>/`) to go
   live, then open it once in Safari so the service worker installs
   the app shell.

Any other static host (or a local web server) works the same way.
Note: the service worker requires HTTPS (GitHub Pages qualifies) or
`localhost`.

## Installing on iPhone

1. Open the published URL in **Safari** on the iPhone.
2. Tap **Share**.
3. Tap **Add to Home Screen**, then **Add**.

Krouchi_DZ then appears on the home screen with its own icon and opens
full-screen like a native app, including offline after the first load.

## Browser caveats

- **CORS:** a web page may only call providers whose API sends CORS
  headers that allow browser calls. Some providers allow this and some
  do not; a provider that blocks browser calls will show a connection
  error in the PWA while the same key keeps working in the Android and
  desktop apps (which are not subject to CORS). This is a browser
  platform rule, not an app bug.
- **Companion mode over plain HTTP:** if the PWA is served over HTTPS
  (for example from GitHub Pages), browsers block calls to the desktop
  companion server on a local `http://192.168.x.x` address as mixed
  content / private-network traffic. To use companion mode from the
  PWA, serve this folder over plain HTTP on the same local network, or
  open it from `localhost`.
