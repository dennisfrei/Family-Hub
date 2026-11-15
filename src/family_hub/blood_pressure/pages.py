"""Blood pressure page (`/vitals/blood-pressure`): readings and trend per person."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from itertools import groupby

from nicegui import app, ui
from nicegui.events import ValueChangeEventArguments

from family_hub import db
from family_hub.blood_pressure import export, service, vision
from family_hub.blood_pressure.chart import blood_pressure_chart
from family_hub.blood_pressure.list_import import import_dialog, pending_person
from family_hub.blood_pressure.photo import photo_buttons
from family_hub.blood_pressure.schemas import ReadingRead, ReadingWrite
from family_hub.blood_pressure.stats import Average, recent_average
from family_hub.config import get_settings
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.schemas import PersonRead
from family_hub.fever.service import local_timezone
from family_hub.ui import i18n
from family_hub.ui.components import day_divider, empty_state, level_label, page_title, plot, section
from family_hub.ui.dialogs import confirm
from family_hub.ui.fields import DateField, TimeField
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame
from family_hub.ui.theme import is_dark
from family_hub.vitals.pages import BLOOD_PRESSURE_PATH, NAME, area_tabs

PATH = BLOOD_PRESSURE_PATH
CHART_READINGS = 30
LISTED_READINGS = 5
HISTORY_PAGE_SIZE = 50
EXPORT_PERIODS = (30, 90, 365)
DEFAULT_EXPORT_PERIOD = 90
MIN_CHART_READINGS = 2
ACCURATE_KEY = "bp_photo_accurate"

Refresh = Callable[[], Awaitable[None]]

i18n.register(
    {
        "bp.data.readings": ("Blutdruckmessungen", "Blood pressure readings"),
        "bp.title": ("Blutdruck", "Blood pressure"),
        "bp.subtitle": ("Messungen und Verlauf", "Readings and trend"),
        "bp.add_reading": ("Messung hinzufügen", "Add reading"),
        "bp.reading_for": ("Blutdruck für {name}", "Blood pressure for {name}"),
        "bp.no_readings": ("Noch keine Messungen", "No readings yet"),
        "bp.all_readings": ("Alle Messungen", "All readings"),
        "bp.history_for": ("Blutdruck von {name}", "Blood pressure of {name}"),
        "bp.history_count": ("Messungen: {count}", "Readings: {count}"),
        "bp.person_missing": ("Person nicht gefunden", "Person not found"),
        "bp.export": ("Bericht", "Report"),
        "bp.export_period": ("Zeitraum", "Period"),
        "bp.export_days": ("Letzte {days} Tage", "Last {days} days"),
        "bp.export_empty": ("Keine Messungen im Zeitraum.", "No readings in this period."),
        "bp.systolic": ("SYS", "SYS"),
        "bp.diastolic": ("DIA", "DIA"),
        "bp.pulse": ("Puls", "Pulse"),
        "bp.values_required": ("SYS und DIA eingeben.", "Enter SYS and DIA."),
        "bp.saved": ("{value} mmHg gespeichert", "{value} mmHg saved"),
        "bp.confirm_delete": ("Messung {value} mmHg löschen?", "Delete reading {value} mmHg?"),
        "bp.from_photo": ("Vom Foto ablesen", "Read from photo"),
        "bp.photo_reading": ("Foto wird ausgewertet …", "Reading the photo …"),
        "bp.photo_accurate": ("Genauer lesen (langsamer)", "Read more accurately (slower)"),
        "bp.photo_check": ("Werte übernommen, bitte prüfen.", "Values filled in, please check."),
        "bp.photo_unreadable": (
            "Keine Werte erkannt. Bitte von Hand eingeben.",
            "No values found. Please enter them by hand.",
        ),
    }
)


def register_pages() -> None:
    """Register the blood pressure page."""

    @ui.page(PATH)
    async def overview_page() -> None:
        with frame(NAME):
            area_tabs("blood_pressure")
            page_title(t("bp.title"), t("bp.subtitle"))
            await _overview()

    @ui.page(f"{PATH}/people/{{person_id}}")
    async def history_page(person_id: int) -> None:
        with frame(NAME):
            area_tabs("blood_pressure")
            await _history(person_id)


def _value(reading: ReadingRead) -> str:
    return f"{reading.systolic}/{reading.diastolic}"


def _limits() -> export.Limits:
    settings = get_settings()
    return (
        (settings.bp_elevated_systolic, settings.bp_elevated_diastolic),
        (settings.bp_high_systolic, settings.bp_high_diastolic),
    )


def _average_line(average: Average | None) -> None:
    if average is None:
        return
    with ui.row().classes("w-full items-baseline gap-2"):
        ui.label(export.average_label(average)).classes("text-sm hub-muted")
        level_label(export.average_value(average), average.level.value, "text-sm font-semibold")


def _number(value: float | None) -> int | None:
    return None if value is None else round(value)


def _fill_from_photo(
    inputs: tuple[ui.number, ui.number, ui.number], accurate: Callable[[], bool]
) -> Callable[[bytes], Awaitable[None]]:
    systolic, diastolic, pulse = inputs

    async def read(photo: bytes) -> None:
        measurement = await vision.read_photo(photo, accurate=accurate())
        if measurement is None:
            ui.notify(t("bp.photo_unreadable"), type="warning")
            return
        systolic.value, diastolic.value, pulse.value = measurement.systolic, measurement.diastolic, measurement.pulse
        ui.notify(t("bp.photo_check"), type="info")

    return read


async def _reading_dialog(person: PersonRead, on_saved: Refresh) -> None:
    now = datetime.now(local_timezone())
    with ui.dialog() as dialog, ui.card().classes("hub-card w-96 max-w-full p-5 gap-3"):
        ui.label(t("bp.reading_for", name=person.name)).classes("text-lg font-semibold")
        photo_slot = ui.column().classes("w-full gap-2")
        with ui.row().classes("w-full gap-3 no-wrap"):
            systolic, diastolic, pulse = (
                ui.number(t(f"bp.{name}"), format="%d", step=1).props("outlined dense").classes("grow min-w-0")
                for name in ("systolic", "diastolic", "pulse")
            )
        if vision.is_enabled():
            with photo_slot:
                with ui.row().classes("w-full items-center justify-between gap-2"):
                    ui.label(t("bp.from_photo")).classes("text-sm hub-muted")
                    if vision.has_accurate_model():
                        ui.switch(
                            t("bp.photo_accurate"),
                            value=app.storage.user.get(ACCURATE_KEY, False),
                            on_change=lambda e: app.storage.user.update({ACCURATE_KEY: e.value}),
                        ).props("dense").classes("text-sm")
                photo_buttons(
                    t("bp.photo_reading"),
                    _fill_from_photo(
                        (systolic, diastolic, pulse),
                        lambda: vision.has_accurate_model() and app.storage.user.get(ACCURATE_KEY, False),
                    ),
                )
        with ui.row().classes("w-full gap-3 no-wrap"):
            date_input = DateField(t("common.date"), now.date())
            time_input = TimeField(t("common.time"), now.time().replace(second=0, microsecond=0))
        note = ui.input(t("common.note_optional")).props("outlined dense").classes("w-full")

        async def save() -> None:
            high, low = _number(systolic.value), _number(diastolic.value)
            if high is None or low is None:
                ui.notify(t("bp.values_required"), type="negative")
                return
            data = ReadingWrite(
                person_id=person.id,
                systolic=high,
                diastolic=low,
                pulse=_number(pulse.value),
                measured_at=datetime.combine(date_input.value or now.date(), time_input.value),
                note=note.value or None,
            )
            try:
                async with db.session() as session:
                    reading = await service.add_reading(session, data)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            ui.notify(t("bp.saved", value=_value(reading)), type="positive")
            dialog.close()
            await on_saved()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.save"), on_click=save).props("unelevated")
    dialog.open()


def _reading_row(
    reading: ReadingRead, on_delete: Callable[[ReadingRead], Awaitable[None]], *, show_date: bool = True
) -> None:
    local = reading.measured_at.astimezone(local_timezone())
    moment = f"{i18n.day(local)} {local:%H:%M}" if show_date else f"{local:%H:%M}"
    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        level_label(_value(reading), reading.level.value, "font-bold text-lg w-24")
        with ui.column().classes("gap-0 grow min-w-0"):
            with ui.row().classes("items-baseline gap-x-2 gap-y-0"):
                if reading.pulse is not None:
                    ui.label(t("bp.pulse_value", value=reading.pulse)).classes("text-sm font-medium whitespace-nowrap")
                ui.label(moment).classes("text-sm hub-muted whitespace-nowrap")
            if reading.note:
                ui.label(reading.note).classes("text-sm truncate")
        ui.button(icon="delete_outline", on_click=lambda: on_delete(reading)).props("flat round dense color=negative")


def _person_header(person: PersonRead, latest: ReadingRead | None, on_change: Refresh) -> None:
    with ui.row().classes("grow items-center no-wrap gap-2 min-w-0"):
        ui.label(person.name).classes("text-lg font-semibold grow truncate")
        if latest is not None:
            ui.label(i18n.short_day(latest.measured_at.astimezone(local_timezone()))).classes("text-sm hub-muted")
            level_label(_value(latest), latest.level.value, "font-bold")
        # click.stop keeps the card from toggling
        if vision.is_enabled():
            with (
                ui.button(icon="document_scanner")
                .props("flat round dense")
                .on("click.stop", lambda: import_dialog(person, on_change))
            ):
                ui.tooltip(t("bp.import_list"))
        with (
            ui.button(icon="add")
            .props("unelevated round dense")
            .on("click.stop", lambda: _reading_dialog(person, on_change))
        ):
            ui.tooltip(t("bp.add_reading"))


def _person_body(
    person: PersonRead, own: list[ReadingRead], on_change: Refresh, on_delete: Callable[[ReadingRead], Awaitable[None]]
) -> None:
    if not own:
        ui.label(t("bp.no_readings")).classes("text-sm hub-muted")
        return
    _average_line(recent_average(own, datetime.now(local_timezone())))
    if len(own) >= MIN_CHART_READINGS:
        settings = get_settings()
        figure = blood_pressure_chart(
            own[::-1],
            local_timezone(),
            limits=(settings.bp_high_systolic, settings.bp_high_diastolic),
            dark=is_dark(),
            day_format=i18n.short_day_format(),
        )
        plot(figure)
    for reading in own[:LISTED_READINGS]:
        _reading_row(reading, on_delete)
    ui.button(t("bp.all_readings"), on_click=lambda: ui.navigate.to(f"{PATH}/people/{person.id}")).props(
        "flat dense no-caps"
    ).classes("self-start")


async def _overview() -> None:
    opened: set[int] = set()

    @ui.refreshable
    async def content() -> None:
        async with db.session() as session:
            people = await core_service.list_people(session)
            readings = {
                person.id: await service.list_readings(session, person_id=person.id, limit=CHART_READINGS)
                for person in people
            }
        if not people:
            with section():
                empty_state(t("core.empty"), t("common.manage_people"), lambda: ui.navigate.to("/people"))
            return

        async def remove(reading: ReadingRead) -> None:
            if not await confirm(t("bp.confirm_delete", value=_value(reading))):
                return
            async with db.session() as session:
                await service.delete_reading(session, reading.id)
            await content.refresh()

        def card(person: PersonRead) -> None:
            own = readings[person.id]

            def toggle(event: ValueChangeEventArguments) -> None:
                if not event.value:
                    opened.discard(person.id)
                    return
                opened.add(person.id)
                # Filled on first opening: a chart drawn while hidden gets the wrong width
                if not list(body):
                    with body:
                        _person_body(person, own, content.refresh, remove)

            with (
                ui.card().classes("hub-card p-0 gap-0 overflow-hidden").style(f"border-top: 4px solid {person.color}"),
                ui.expansion(value=person.id in opened, on_value_change=toggle).classes("w-full") as expansion,
            ):
                with expansion.add_slot("header"):
                    _person_header(person, own[0] if own else None, content.refresh)
                with ui.column().classes("w-full gap-2 pb-2") as body:
                    if person.id in opened:
                        _person_body(person, own, content.refresh, remove)

        people.sort(key=lambda p: (p.kind is not PersonKind.ADULT, p.name))
        with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2 items-start"):
            for person in people:
                card(person)

    await content()

    async def resume() -> None:
        person_id = pending_person()
        if person_id is None:
            return
        async with db.session() as session:
            people = {person.id: person for person in await core_service.list_people(session)}
        if person_id in people:
            await import_dialog(people[person_id], content.refresh)

    if vision.is_enabled():
        ui.timer(0, resume, once=True)


async def _history(person_id: int) -> None:
    async with db.session() as session:
        try:
            person = await core_service.get_person(session, person_id)
        except core_service.PersonNotFoundError:
            with section():
                empty_state(t("bp.person_missing"), t("bp.title"), lambda: ui.navigate.to(PATH))
            return
    state = {"page": 1}

    @ui.refreshable
    async def content() -> None:
        async with db.session() as session:
            count = await service.count_readings(session, person.id)
            pages = max(1, -(-count // HISTORY_PAGE_SIZE))
            state["page"] = min(state["page"], pages)
            readings = await service.list_readings(
                session, person_id=person.id, limit=HISTORY_PAGE_SIZE, offset=(state["page"] - 1) * HISTORY_PAGE_SIZE
            )

        async def remove(reading: ReadingRead) -> None:
            if not await confirm(t("bp.confirm_delete", value=_value(reading))):
                return
            async with db.session() as session:
                await service.delete_reading(session, reading.id)
            await content.refresh()

        async def turn(event: ValueChangeEventArguments) -> None:
            state["page"] = int(event.value)
            await content.refresh()

        with section():
            if not readings:
                ui.label(t("bp.no_readings")).classes("text-sm hub-muted")
                return
            ui.label(t("bp.history_count", count=count)).classes("text-sm hub-muted")
            if state["page"] == 1:
                _average_line(recent_average(readings, datetime.now(local_timezone())))
            month = None
            for day, day_readings in groupby(readings, key=lambda r: r.measured_at.astimezone(local_timezone()).date()):
                if (day.year, day.month) != month:
                    month = (day.year, day.month)
                    ui.label(i18n.month_year(day)).classes("text-base font-semibold mt-3")
                items = list(day_readings)
                day_divider(f"{i18n.weekday(day.weekday())} · {i18n.day(day)}", len(items))
                for reading in items:
                    _reading_row(reading, remove, show_date=False)
            if pages > 1:
                ui.pagination(1, pages, direction_links=True, value=state["page"], on_change=turn).props(
                    "max-pages=5 boundary-numbers"
                ).classes("self-center mt-2")

    with ui.row().classes("w-full items-center gap-2 no-wrap"):
        ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to(PATH)).props("flat round dense")
        ui.label(t("bp.history_for", name=person.name)).classes("text-xl font-semibold")
    _export_section(person)
    await content()


def _export_section(person: PersonRead) -> None:
    periods: dict[int, str] = {days: t("bp.export_days", days=days) for days in EXPORT_PERIODS} | {0: t("common.all")}

    async def download(kind: str) -> None:
        now = datetime.now(local_timezone())
        since = now - timedelta(days=period.value) if period.value else None
        async with db.session() as session:
            readings = await service.list_readings(session, person_id=person.id, since=since)
        if not readings:
            ui.notify(t("bp.export_empty"), type="warning")
            return
        report = (person.name, readings, recent_average(readings, now), _limits(), local_timezone())
        name = t("bp.report_title", name=person.name)
        if kind == "pdf":
            ui.download.content(export.to_pdf(*report), f"{name}.pdf", "application/pdf")
        else:
            ui.download.content(export.to_html(*report), f"{name}.html", "text/html")

    with section(t("bp.export")), ui.row().classes("w-full items-center gap-2"):
        period = (
            ui.select(periods, value=DEFAULT_EXPORT_PERIOD, label=t("bp.export_period"))
            .props("outlined dense")
            .classes("grow min-w-0")
        )
        ui.button("PDF", icon="picture_as_pdf", on_click=lambda: download("pdf")).props("outline")
        ui.button("HTML", icon="description", on_click=lambda: download("html")).props("outline")
