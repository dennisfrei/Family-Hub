"""Reusable dialogs."""

from nicegui import ui

from family_hub.ui.i18n import t


async def confirm(message: str, *, ok_label: str | None = None) -> bool:
    """Ask for confirmation; returns True if confirmed."""
    with ui.dialog() as dialog, ui.card().classes("hub-card p-5 gap-4"):
        ui.label(message).classes("text-base")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(ok_label or t("common.delete"), on_click=lambda: dialog.submit(True)).props(
                "unelevated color=negative"
            )
    result = await dialog
    dialog.delete()
    return bool(result)
