"""Dialog that reads a photo of a written list of readings and saves the lines the user approves.

Reading runs apart from the page and is kept per browser, so it survives a reload while the phone sleeps.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, time, timedelta

from nicegui import app, ui
from pydantic import BaseModel, ConfigDict

from family_hub import db
from family_hub.blood_pressure import service, vision
from family_hub.blood_pressure.photo import photo_buttons
from family_hub.blood_pressure.schemas import ListEntry, Measurement, ReadingRead, ReadingWrite
from family_hub.core.schemas import PersonRead
from family_hub.fever.service import local_timezone
from family_hub.ui import i18n
from family_hub.ui.fields import DateField, TimeField
from family_hub.ui.i18n import t

logger = logging.getLogger(__name__)

DEFAULT_TIME = time(8, 0)
KEEP_JOB = timedelta(minutes=30)
OLD_AFTER = timedelta(days=365)
USUAL_MIN_SYSTOLIC = 100
USUAL_MIN_SPREAD = 20

Refresh = Callable[[], Awaitable[None]]
Taken = set[tuple[datetime, int, int]]

i18n.register(
    {
        "bp.import_list": ("Liste vom Foto übernehmen", "Import a list from a photo"),
        "bp.import_for": ("Liste für {name} übernehmen", "Import a list for {name}"),
        "bp.import_intro": (
            "Foto einer Liste mit Datum, Uhrzeit und Werten. Vor dem Speichern kannst du jede Zeile prüfen.",
            "Photo of a list with date, time and values. You can check every line before saving.",
        ),
        "bp.import_reading": (
            "Liste wird gelesen, das dauert bis zu zwei Minuten.",
            "Reading the list, this takes up to two minutes.",
        ),
        "bp.import_empty": (
            "Keine Messungen erkannt. Ein schärferes, gerades Foto hilft.",
            "No readings found. A sharper, straight photo helps.",
        ),
        "bp.import_found": (
            "Erkannte Zeilen: {count}. Bitte mit der Liste vergleichen.",
            "Lines found: {count}. Please compare with the list.",
        ),
        "bp.import_save": ("Auswahl speichern ({count})", "Save selection ({count})"),
        "bp.import_saved": ("Messungen gespeichert: {count}", "Readings saved: {count}"),
        "bp.import_none_selected": ("Keine Zeile ausgewählt.", "No line selected."),
        "bp.import_check_rows": ("Bitte die markierten Zeilen prüfen.", "Please check the marked lines."),
        "bp.import_no_date": ("Datum fehlt", "Date missing"),
        "bp.import_no_time": ("Uhrzeit nicht erkannt", "Time not recognised"),
        "bp.import_no_values": ("SYS oder DIA fehlt", "SYS or DIA missing"),
        "bp.import_unusual": ("Werte ungewöhnlich, bitte prüfen", "Unusual values, please check"),
        "bp.import_old": ("Datum liegt über ein Jahr zurück", "Date is more than a year ago"),
        "bp.import_future": ("Datum liegt in der Zukunft", "Date is in the future"),
        "bp.import_duplicate": ("schon vorhanden", "already recorded"),
    }
)


class _Job(BaseModel):
    """A list photo being read, or its result."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    person_id: int
    task: asyncio.Task[list[ListEntry]]
    started: datetime


_jobs: dict[str, _Job] = {}


def _job() -> _Job | None:
    """The current browser's job, if it is recent."""
    now = datetime.now(local_timezone())
    for key in [key for key, job in _jobs.items() if now - job.started > KEEP_JOB]:
        _jobs.pop(key).task.cancel()
    return _jobs.get(app.storage.browser["id"])


def _drop_job() -> None:
    job = _jobs.pop(app.storage.browser["id"], None)
    if job is not None:
        job.task.cancel()


def pending_person() -> int | None:
    """The person whose list this browser was reading before the page was reloaded."""
    job = _job()
    return None if job is None else job.person_id


def _today() -> date:
    return datetime.now(local_timezone()).date()


def _number(value: float | None) -> int | None:
    return None if value is None else round(value)


def _key(measured_at: datetime, systolic: int, diastolic: int) -> tuple[datetime, int, int]:
    return measured_at.replace(second=0, microsecond=0, tzinfo=None), systolic, diastolic


class _Row:
    """One line of the list as editable fields."""

    def __init__(self, entry: ListEntry, taken: Taken, on_toggle: Callable[[], None]) -> None:
        self._taken = taken
        with ui.column().classes("w-full gap-1 py-2").style("border-bottom: 1px solid rgba(128, 128, 128, 0.25)"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                self.include = ui.checkbox(value=True, on_change=on_toggle).props("dense")
                self.day = DateField(t("common.date"), entry.day)
                self.at = TimeField(t("common.time"), entry.at or DEFAULT_TIME)
            with ui.row().classes("w-full gap-2 no-wrap pl-8"):
                self.systolic, self.diastolic, self.pulse = (
                    ui.number(t(f"bp.{name}"), value=value, format="%d", step=1)
                    .props("outlined dense")
                    .classes("grow min-w-0")
                    for name, value in (
                        ("systolic", entry.systolic),
                        ("diastolic", entry.diastolic),
                        ("pulse", entry.pulse),
                    )
                )
            self.hint = ui.label().classes("text-xs text-orange-600 pl-8")
        notes = []
        if entry.at is None:
            notes.append(t("bp.import_no_time"))
        if self._duplicate():
            notes.append(t("bp.import_duplicate"))
            self.include.value = False
        self.check(notes)

    def _values(self) -> Measurement | None:
        high, low = _number(self.systolic.value), _number(self.diastolic.value)
        if high is None or low is None:
            return None
        return Measurement(systolic=high, diastolic=low, pulse=_number(self.pulse.value))

    def _measured_at(self) -> datetime | None:
        return datetime.combine(self.day.value, self.at.value) if self.day.value else None

    def _duplicate(self) -> bool:
        measured_at, values = self._measured_at(), self._values()
        if measured_at is None or values is None:
            return False
        return _key(measured_at, values.systolic, values.diastolic) in self._taken

    def _errors(self) -> list[str]:
        errors = []
        if self.day.value is None:
            errors.append(t("bp.import_no_date"))
        elif self.day.value > _today():
            errors.append(t("bp.import_future"))
        values = self._values()
        if values is None:
            errors.append(t("bp.import_no_values"))
        else:
            try:
                service.validate(values)
            except ValueError as exc:
                errors.append(i18n.error_text(exc))
        return errors

    def check(self, notes: list[str] | None = None) -> bool:
        """Show what is wrong with the line; returns whether it can be saved."""
        errors = self._errors()
        old = [t("bp.import_old")] if self.day.value and _today() - self.day.value > OLD_AFTER else []
        values = self._values()
        low = values is not None and (
            values.systolic < USUAL_MIN_SYSTOLIC or values.systolic - values.diastolic < USUAL_MIN_SPREAD
        )
        unusual = [t("bp.import_unusual")] if low and not errors else []
        texts = [*errors, *unusual, *old, *(notes or [])]
        self.hint.text = " · ".join(texts)
        self.hint.set_visibility(bool(texts))
        return not errors

    def reading(self, person_id: int) -> ReadingWrite | None:
        """The line as a new reading; None while values or the date are missing."""
        measured_at, values = self._measured_at(), self._values()
        if measured_at is None or values is None:
            return None
        return ReadingWrite(person_id=person_id, measured_at=measured_at, **values.model_dump())


def _taken(readings: list[ReadingRead]) -> Taken:
    zone = local_timezone()
    return {_key(reading.measured_at.astimezone(zone), reading.systolic, reading.diastolic) for reading in readings}


async def import_dialog(person: PersonRead, on_saved: Refresh) -> None:
    """Open the dialog to import a photographed list for a person."""
    async with db.session() as session:
        taken = _taken(await service.list_readings(session, person_id=person.id))
    rows: list[_Row] = []

    def selected() -> list[_Row]:
        return [row for row in rows if row.include.value]

    def update_save() -> None:
        save_button.text = t("bp.import_save", count=len(selected()))
        save_button.set_visibility(bool(rows))

    async def read(photo: bytes) -> None:
        _drop_job()
        task = asyncio.create_task(vision.read_list(photo, _today()))
        _jobs[app.storage.browser["id"]] = _Job(person_id=person.id, task=task, started=datetime.now(local_timezone()))
        await show(task)

    async def resume(task: asyncio.Task[list[ListEntry]]) -> None:
        waiting.set_visibility(True)
        try:
            await show(task)
        except vision.VisionError as exc:
            logger.warning(f"Reading the list failed: {exc}")
            ui.notify(t("bp.photo_failed"), type="warning")
        finally:
            if not dialog.is_deleted:
                waiting.set_visibility(False)

    async def show(task: asyncio.Task[list[ListEntry]]) -> None:
        try:
            entries = await asyncio.shield(task)
        except vision.VisionError:
            _drop_job()
            raise
        if dialog.is_deleted:
            return
        rows.clear()
        lines.clear()
        with lines:
            rows.extend(_Row(entry, taken, update_save) for entry in entries)
        summary.text = t("bp.import_found", count=len(entries)) if entries else t("bp.import_empty")
        summary.set_visibility(True)
        update_save()

    async def save() -> None:
        chosen = selected()
        if not chosen:
            ui.notify(t("bp.import_none_selected"), type="negative")
            return
        readings = [reading for row in chosen if row.check() and (reading := row.reading(person.id))]
        if len(readings) < len(chosen):
            ui.notify(t("bp.import_check_rows"), type="negative")
            return
        try:
            async with db.session() as session:
                saved = await service.add_readings(session, readings)
        except ValueError as exc:
            ui.notify(i18n.error_text(exc), type="negative")
            return
        ui.notify(t("bp.import_saved", count=len(saved)), type="positive")
        _drop_job()
        dialog.close()
        await on_saved()

    def cancel() -> None:
        _drop_job()
        dialog.close()

    with ui.dialog().props("persistent") as dialog, ui.card().classes("hub-card w-[32rem] max-w-full p-5 gap-3"):
        ui.label(t("bp.import_for", name=person.name)).classes("text-lg font-semibold")
        ui.label(t("bp.import_intro")).classes("text-sm hub-muted")
        photo_buttons(t("bp.import_reading"), read)
        with ui.row().classes("w-full items-center gap-2 no-wrap") as waiting:
            ui.spinner(size="sm")
            ui.label(t("bp.import_reading")).classes("text-sm hub-muted")
        waiting.set_visibility(False)
        summary = ui.label().classes("text-sm font-medium")
        summary.set_visibility(False)
        lines = ui.column().classes("w-full gap-0 overflow-y-auto").style("max-height: 50vh")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=cancel).props("flat")
            save_button = ui.button(on_click=save).props("unelevated no-caps")
    update_save()
    dialog.open()
    job = _job()
    if job is not None and job.person_id == person.id:
        await resume(job.task)
