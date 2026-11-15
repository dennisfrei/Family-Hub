"""Shared parts of the vitals pages: the switch between areas and redirects from the old fever paths."""

from nicegui import ui

from family_hub.ui import i18n
from family_hub.ui.i18n import t

NAME = "vitals"
PATH = "/vitals"
FEVER_PATH = f"{PATH}/fever"
BLOOD_PRESSURE_PATH = f"{PATH}/blood-pressure"

AREAS = (
    ("fever", "fever.title", FEVER_PATH),
    ("blood_pressure", "bp.title", BLOOD_PRESSURE_PATH),
)

i18n.register({"vitals.title": ("Gesundheit", "Health")})


def area_tabs(active: str) -> None:
    """Buttons to switch between the vitals areas; `active` is the current area's name."""
    with ui.row().classes("w-full gap-2 no-print"):
        for name, label_key, path in AREAS:
            ui.button(t(label_key), on_click=lambda p=path: ui.navigate.to(p)).props(
                f"no-caps {'unelevated' if name == active else 'outline'}"
            )


def register_pages() -> None:
    """Register the entry page and redirects for bookmarks of the earlier fever paths."""

    @ui.page(PATH)
    def entry_page() -> None:
        ui.navigate.to(FEVER_PATH)

    @ui.page("/fever")
    def old_overview_page() -> None:
        ui.navigate.to(FEVER_PATH)

    @ui.page("/fever/episodes/{episode_id}")
    def old_episode_page(episode_id: int) -> None:
        ui.navigate.to(f"{FEVER_PATH}/episodes/{episode_id}")
