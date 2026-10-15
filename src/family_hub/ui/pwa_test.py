from family_hub.ui import pwa


def test_manifest_uses_prefix() -> None:
    manifest = pwa.manifest("/proxy/8080")

    assert manifest["start_url"] == "/proxy/8080/"
    assert manifest["scope"] == "/proxy/8080/"
    icons = manifest["icons"]
    assert isinstance(icons, list)
    assert all(icon["src"].startswith("/proxy/8080/static/") for icon in icons)


def test_manifest_without_prefix() -> None:
    assert pwa.manifest("")["start_url"] == "/"


def test_service_worker_and_head() -> None:
    assert "const PREFIX = '/p';" in pwa.service_worker("/p")
    head = pwa.head_html("/p", dark=True)
    assert 'href="/p/manifest.webmanifest"' in head
    assert "register('/p/sw.js', {scope: '/p/'})" in head


def test_icons_exist() -> None:
    for name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png", "favicon.png"):
        assert (pwa.STATIC_DIR / name).is_file()


def test_service_worker_never_caches_redirects_or_pages() -> None:
    source = pwa.service_worker("/proxy/8080")

    assert "!response.redirected" in source
    assert "!type.startsWith('text/html')" in source
