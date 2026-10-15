"""Progressive web app: manifest, service worker, icons and head tags (prefix-aware for path proxies)."""

import json
from pathlib import Path

from fastapi.responses import HTMLResponse, Response
from nicegui import __version__ as nicegui_version
from nicegui import app, ui

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_PATH = "/static"
CACHE_VERSION = "family-hub-v2"
DARK_BACKGROUND = "#111316"
LIGHT_BACKGROUND = "#f5f5f3"

OFFLINE_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Family Hub</title>
<style>body{font-family:system-ui,sans-serif;background:#111316;color:#e6e7e9;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;text-align:center}button{margin-top:16px;padding:8px 16px;border-radius:8px;
border:1px solid #4fb3a2;background:transparent;color:#4fb3a2;font-size:16px}</style></head>
<body><div><h2>Keine Verbindung</h2><p>Family Hub ist gerade nicht erreichbar.<br>No connection.</p>
<button onclick="location.reload()">Neu laden / Reload</button></div></body></html>"""

SERVICE_WORKER = """
const CACHE = '%(cache)s';
const PREFIX = '%(prefix)s';
const STATIC = [PREFIX + '/offline.html', PREFIX + '/static/icon-192.png', PREFIX + '/static/icon-512.png'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match(PREFIX + '/offline.html')));
    return;
  }
  if (url.pathname.startsWith(PREFIX + '/_nicegui/%(version)s/static/') || url.pathname.startsWith(PREFIX + '/static/')) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        const type = response.headers.get('content-type') || '';
        if (response.ok && !response.redirected && response.type === 'basic' && !type.startsWith('text/html')) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
        }
        return response;
      }))
    );
  }
});
"""


def manifest(prefix: str) -> dict[str, object]:
    """Web app manifest for the given path prefix."""
    return {
        "name": "Family Hub",
        "short_name": "Family Hub",
        "start_url": f"{prefix}/",
        "scope": f"{prefix}/",
        "display": "standalone",
        "orientation": "any",
        "background_color": DARK_BACKGROUND,
        "theme_color": DARK_BACKGROUND,
        "lang": "de",
        "icons": [
            {"src": f"{prefix}{STATIC_PATH}/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": f"{prefix}{STATIC_PATH}/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {
                "src": f"{prefix}{STATIC_PATH}/icon-maskable-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }


def service_worker(prefix: str) -> str:
    """Service worker source: cached static assets and an offline page for navigations."""
    return SERVICE_WORKER % {"cache": CACHE_VERSION, "prefix": prefix, "version": nicegui_version}


def head_html(prefix: str, *, dark: bool) -> str:
    """Head tags for installability on Android and iOS, and the service worker registration."""
    theme_color = DARK_BACKGROUND if dark else LIGHT_BACKGROUND
    return f"""
<link rel="manifest" href="{prefix}/manifest.webmanifest">
<meta name="theme-color" content="{theme_color}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="{"black-translucent" if dark else "default"}">
<meta name="apple-mobile-web-app-title" content="Family Hub">
<link rel="apple-touch-icon" href="{prefix}{STATIC_PATH}/apple-touch-icon.png">
<script>
  if ('serviceWorker' in navigator) {{
    window.addEventListener('load', () => navigator.serviceWorker.register('{prefix}/sw.js', {{scope: '{prefix}/'}}));
  }}
</script>
"""


def register(prefix: str) -> None:
    """Serve icons, manifest, service worker and offline page."""
    prefix = prefix.rstrip("/")
    app.add_static_files(STATIC_PATH, STATIC_DIR)

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def _manifest() -> Response:
        return Response(json.dumps(manifest(prefix)), media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def _service_worker() -> Response:
        return Response(
            service_worker(prefix),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": f"{prefix}/", "Cache-Control": "no-cache"},
        )

    @app.get("/offline.html", include_in_schema=False)
    def _offline() -> HTMLResponse:
        return HTMLResponse(OFFLINE_HTML)


def add_head(prefix: str, *, dark: bool) -> None:
    """Add the PWA head tags to the current page."""
    ui.add_head_html(head_html(prefix.rstrip("/"), dark=dark))
