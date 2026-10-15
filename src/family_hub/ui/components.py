"""Reusable UI building blocks with the shared look."""

from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager

import plotly.graph_objects as go
from nicegui import ui

from family_hub.ui.theme import LEVEL_TEXT_CLASSES

Action = Callable[[], Awaitable[None] | None]


@contextmanager
def section(title: str | None = None, *, toolbar: bool = False, classes: str = "") -> Generator[ui.row]:
    """A card with an optional title row; yields the title row for extra actions (`toolbar` keeps it without title)."""
    with ui.card().classes(f"w-full p-4 gap-3 hub-card {classes}"):
        with ui.row().classes("w-full items-center gap-2") as header:
            if title:
                ui.label(title).classes("text-base font-semibold grow")
        if not (title or toolbar):
            header.set_visibility(False)
        yield header


def page_title(title: str, subtitle: str | None = None) -> ui.row:
    """Page heading; returns the row so callers can add actions."""
    with ui.row().classes("w-full items-end gap-3") as row, ui.column().classes("gap-0 grow min-w-0"):
        ui.label(title).classes("text-2xl font-semibold")
        if subtitle:
            ui.label(subtitle).classes("text-sm hub-muted")
    return row


def stat_tile(label: str, value: str, detail: str | None = None, *, accent: str | None = None) -> None:
    """A small metric tile; `accent` colors the dot before the label."""
    with ui.card().classes("p-3 gap-0 hub-card hub-tile"):
        with ui.row().classes("items-center gap-2 no-wrap"):
            if accent:
                ui.element("div").classes("rounded-full shrink-0").style(f"background:{accent}; width:8px; height:8px")
            ui.label(label).classes("text-xs hub-muted truncate")
        ui.label(value).classes("text-xl font-semibold")
        if detail:
            ui.label(detail).classes("text-xs hub-muted")


def empty_state(text: str, action_label: str | None = None, on_action: Action | None = None) -> None:
    """Hint for empty lists."""
    with ui.column().classes("w-full items-center gap-3 py-4"):
        ui.label(text).classes("hub-muted text-center")
        if action_label and on_action:
            ui.button(action_label, on_click=on_action).props("unelevated")


def person_chip(name: str, color: str, *, selected: bool = True, on_click: Action | None = None) -> ui.element:
    """Rounded chip with the person's color."""
    style = (
        f"background-color: {color}; color: white; border: 1px solid {color}"
        if selected
        else f"border: 1px solid {color}; color: {color}"
    )
    chip = ui.element("div").classes("hub-chip cursor-pointer select-none").style(style)
    with chip:
        ui.label(name).classes("text-sm font-medium")
    if on_click is not None:
        chip.on("click", on_click)
    return chip


def person_dot(color: str, size: int = 10) -> None:
    """Small colored dot for a person or type."""
    ui.element("div").classes("rounded-full shrink-0").style(f"background:{color}; width:{size}px; height:{size}px")


def level_label(text: str, level: str, classes: str = "font-semibold") -> ui.label:
    """Text colored by level (normal / elevated / fever)."""
    return ui.label(text).classes(f"{classes} {LEVEL_TEXT_CLASSES.get(level, '')}")


def day_divider(text: str, count: int | None = None) -> None:
    """Separator between days in a list, as in the earlier fever app."""
    with ui.row().classes("w-full items-center gap-2 mt-2 no-wrap"):
        ui.label(text).classes("text-sm font-medium hub-muted whitespace-nowrap")
        ui.element("div").classes("hub-divider")
        if count is not None:
            ui.label(str(count)).classes("text-xs hub-muted")


def plot(figure: go.Figure) -> ui.plotly:
    """Render a Plotly figure responsive and without toolbar."""
    figure.update_layout(autosize=True, width=None)
    data = figure.to_plotly_json()
    data["config"] = {"displayModeBar": False, "responsive": True}
    return ui.plotly(data).classes("w-full min-w-0").style("max-width: 100%")
