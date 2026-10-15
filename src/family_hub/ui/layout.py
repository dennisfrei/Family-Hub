"""Shared page frame: header with dark mode and language switch, navigation drawer, content column."""

from collections.abc import Generator
from contextlib import contextmanager

from nicegui import context, ui

from family_hub.module import Module
from family_hub.oidc import LOGOUT_PATH, SessionUser, current_user
from family_hub.ui import i18n
from family_hub.ui.i18n import Language, t
from family_hub.ui.theme import apply_theme, is_dark, set_dark

_navigation: list[Module] = []

i18n.register({"app.title": ("Family Hub", "Family Hub")})


def set_navigation(modules: list[Module]) -> None:
    """Set the modules shown in the navigation drawer."""
    _navigation[:] = [module for module in modules if module.in_navigation]


def signed_in_user() -> SessionUser | None:
    """The signed-in user of the current page; None without login or outside a request."""
    try:
        request = context.client.request
    except RuntimeError:
        return None
    return current_user(request)


def _visible_modules(user: SessionUser | None) -> list[Module]:
    return [module for module in _navigation if user is None or user.is_admin or not module.admin_only]


def _user_menu(user: SessionUser) -> None:
    with ui.button(user.name[:1].upper()).props("flat round dense").classes("hub-avatar"), ui.menu():
        with ui.column().classes("px-4 py-3 gap-0"):
            ui.label(user.name).classes("font-medium")
            if user.email:
                ui.label(user.email).classes("text-xs hub-muted")
        ui.separator()
        ui.menu_item(t("layout.logout"), on_click=lambda: ui.navigate.to(LOGOUT_PATH))


def _toggle_dark() -> None:
    set_dark(not is_dark())
    ui.navigate.reload()


def _switch_language() -> None:
    i18n.set_language(Language.EN if i18n.language() is Language.DE else Language.DE)
    ui.navigate.reload()


def _navigation_drawer(active: str, user: SessionUser | None) -> ui.left_drawer:
    with (
        ui.left_drawer(value=None, bordered=False)
        .props("width=240 breakpoint=1024")
        .classes("hub-drawer p-0") as drawer,
        ui.column().classes("w-full h-full gap-0 no-wrap"),
    ):
        ui.label(t("app.title")).classes("text-lg font-semibold px-5 py-5")
        modules = _visible_modules(user)
        _navigation_list([m for m in modules if not m.navigation_bottom], active)
        ui.space()
        _navigation_list([m for m in modules if m.navigation_bottom], active, classes="pb-3")
    return drawer


def _navigation_list(modules: list[Module], active: str, classes: str = "") -> None:
    if not modules:
        return
    with ui.list().classes(f"w-full px-2 {classes}"):
        for module in modules:
            item = ui.item(on_click=lambda path=module.path: ui.navigate.to(path)).classes("rounded-lg mb-1")
            if module.name == active:
                item.classes("hub-nav-active")
            with item:
                with ui.item_section().props("avatar"):
                    ui.icon(module.icon)
                ui.item_section(t(module.label_key))


@contextmanager
def frame(active: str, title: str | None = None, *, wide: bool = False) -> Generator[ui.column]:
    """Render the page frame and yield the content column.

    Args:
        active: Name of the module whose navigation entry is highlighted.
        title: Header title; defaults to the module label.
        wide: Use more of large screens, e.g. for week grids.
    """
    apply_theme()
    user = signed_in_user()
    drawer = _navigation_drawer(active, user)
    module = next((m for m in _navigation if m.name == active), None)
    header_title = title or (t(module.label_key) if module else t("app.title"))
    with ui.header(elevated=False).classes("hub-header items-center gap-1 px-2 py-1 no-print"):
        ui.button(icon="menu", on_click=drawer.toggle).props("flat round").classes("lg:hidden")
        ui.label(header_title).classes("text-base font-semibold grow truncate")
        ui.button(i18n.language().value.upper(), on_click=_switch_language).props("flat dense").tooltip(
            t("layout.language")
        )
        ui.button(icon="light_mode" if is_dark() else "dark_mode", on_click=_toggle_dark).props("flat round").tooltip(
            t("layout.dark_mode")
        )
        ui.button(icon="refresh", on_click=ui.navigate.reload).props("flat round").tooltip(t("layout.refresh"))
        if user is not None:
            _user_menu(user)
    width = "max-w-7xl" if wide else "max-w-5xl"
    with ui.column().classes(f"w-full {width} mx-auto px-3 sm:px-6 py-4 gap-4 min-w-0") as content:
        yield content
