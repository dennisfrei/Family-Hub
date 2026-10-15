"""Colors, CSS and per-browser dark mode, shared by all pages and charts."""

from nicegui import app, ui

from family_hub.config import get_settings
from family_hub.ui import pwa

PRIMARY = "#1f6f63"
PRIMARY_LIGHT = "#4fb3a2"
SECONDARY = "#64748b"
DARK_STORAGE_KEY = "dark"

LEVEL_TEXT_CLASSES = {"normal": "text-green-600", "elevated": "text-orange-500", "fever": "text-red-500"}

CSS = """
:root { --hub-bg: #f5f5f3; --hub-card: #ffffff; --hub-text: #1f2328; --hub-muted: #6b7280; --hub-border: #e4e4e0;
        --hub-accent: #1f6f63; --hub-accent-soft: rgba(31, 111, 99, .10); }
.body--dark { --hub-bg: #111316; --hub-card: #181b1f; --hub-text: #e6e7e9; --hub-muted: #9aa1ab; --hub-border: #2a2e34;
              --hub-accent: #4fb3a2; --hub-accent-soft: rgba(79, 179, 162, .14); }
html, body { background: var(--hub-bg) !important; color: var(--hub-text); overflow-x: hidden; }
.hub-card { background: var(--hub-card) !important; border: 1px solid var(--hub-border); border-radius: 12px !important;
            box-shadow: none !important; min-width: 0; max-width: 100%; }
.hub-muted { color: var(--hub-muted); }
.hub-accent { color: var(--hub-accent); }
.hub-avatar { background: var(--hub-accent-soft) !important; color: var(--hub-accent) !important; font-weight: 600; }
.hub-tile { min-width: 0; flex: 1 1 9rem; }
.hub-chip { padding: 3px 12px; border-radius: 999px; transition: transform .1s; white-space: nowrap; }
.hub-chip:active { transform: scale(.96); }
.hub-header { background: var(--hub-card) !important; color: var(--hub-text) !important;
              border-bottom: 1px solid var(--hub-border); padding-top: env(safe-area-inset-top); }
.hub-nav-active { background: var(--hub-accent-soft); color: var(--hub-accent); font-weight: 600; }
.hub-drawer { background: var(--hub-card) !important; border-right: 1px solid var(--hub-border); }
.hub-divider { flex: 1 1 auto; height: 1px; background: var(--hub-border); }
.nicegui-content { padding: 0 !important; }
.q-btn { border-radius: 8px; text-transform: none; font-weight: 500; letter-spacing: 0; }
.q-tab { color: var(--hub-muted); text-transform: none; }
.q-tab--active { color: var(--hub-accent); }
.q-btn-toggle { border: 1px solid var(--hub-border); border-radius: 8px; overflow: hidden; }
.js-plotly-plot, .js-plotly-plot .plot-container { max-width: 100%; }
.q-field--readonly.q-field--outlined .q-field__control:before { border-style: solid; }
.q-field--readonly .q-field__native { cursor: pointer; }
.q-page-container { padding-bottom: env(safe-area-inset-bottom); }
@media print {
  .q-header, .q-drawer, .no-print { display: none !important; }
  .q-page-container { padding: 0 !important; }
  body { background: white !important; }
}
"""


def is_dark() -> bool:
    """Whether the current browser uses dark mode (default: dark, as in the earlier fever app)."""
    try:
        return bool(app.storage.user.get(DARK_STORAGE_KEY, True))
    except (RuntimeError, AssertionError):
        return True


def set_dark(value: bool) -> None:
    """Remember dark mode for the current browser."""
    app.storage.user[DARK_STORAGE_KEY] = value


def accent() -> str:
    """Accent color for the current mode, e.g. for chart lines."""
    return PRIMARY_LIGHT if is_dark() else PRIMARY


def apply_theme() -> None:
    """Apply colors, CSS and dark mode to the current page."""
    ui.colors(primary=accent(), secondary=SECONDARY)
    ui.add_css(CSS)
    ui.dark_mode(is_dark())
    pwa.add_head(get_settings().forwarded_prefix, dark=is_dark())
