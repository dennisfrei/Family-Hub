"""Buttons that take or pick a photo and hand it to a vision reader."""

import logging
from collections.abc import Awaitable, Callable

from nicegui import ui
from nicegui.events import UploadEventArguments

from family_hub.blood_pressure import vision
from family_hub.ui import i18n
from family_hub.ui.i18n import t

logger = logging.getLogger(__name__)

i18n.register(
    {
        "bp.photo_take": ("Kamera", "Camera"),
        "bp.photo_album": ("Album", "Album"),
        "bp.photo_failed": (
            "Die Auswertung ist gerade nicht erreichbar. Bitte von Hand eingeben.",
            "Photo reading is unavailable right now. Please enter the values by hand.",
        ),
    }
)


def photo_buttons(busy_text: str, on_photo: Callable[[bytes], Awaitable[None]]) -> None:
    """Show buttons for the camera and the photo album, and a busy line while `on_photo` runs.

    A `vision.VisionError` from `on_photo` is shown as a warning.
    """
    uploads: list[ui.upload] = []
    buttons: list[ui.button] = []

    async def read(event: UploadEventArguments) -> None:
        for button in buttons:
            button.disable()
        status.set_visibility(True)
        try:
            await on_photo(await event.file.read())
        except vision.VisionError as exc:
            logger.warning(f"Reading the photo failed: {exc}")
            ui.notify(t("bp.photo_failed"), type="warning")
        finally:
            for upload in uploads:
                upload.reset()
            status.set_visibility(False)
            for button in buttons:
                button.enable()

    with ui.row().classes("w-full gap-2 no-wrap"):
        for key, icon, capture in (
            ("bp.photo_take", "photo_camera", " capture=environment"),
            ("bp.photo_album", "photo_library", ""),
        ):
            upload = ui.upload(on_upload=read, auto_upload=True, max_files=1).classes("hidden")
            upload.props(f'accept="image/*"{capture}')
            uploads.append(upload)
            # Opened in the browser so the click still counts as a user gesture
            button = ui.button(t(key), icon=icon).props("outline no-caps").classes("grow basis-0 min-w-0")
            button.on("click", js_handler=f"() => getElement({upload.id}).$refs.qRef.pickFiles()")
            buttons.append(button)
    with ui.row().classes("w-full items-center gap-2 no-wrap") as status:
        ui.spinner(size="sm")
        ui.label(busy_text).classes("text-sm hub-muted")
    status.set_visibility(False)
