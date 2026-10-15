"""Fever pages: overview (`/fever`) and episode detail (`/fever/episodes/{id}`)."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from itertools import groupby

from nicegui import app, ui

from family_hub import db
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.schemas import PersonRead
from family_hub.fever import service
from family_hub.fever.chart import INTERPOLATION_LABELS, Interpolation, fever_chart
from family_hub.fever.models import Method
from family_hub.fever.schemas import (
    EpisodeDetail,
    EpisodeRead,
    EpisodeUpdate,
    EpisodeWrite,
    QuickReadingWrite,
    ReadingRead,
    ReadingWrite,
)
from family_hub.ui import i18n
from family_hub.ui.components import day_divider, empty_state, level_label, page_title, person_dot, plot, section
from family_hub.ui.dialogs import confirm
from family_hub.ui.fields import DateField, TimeField
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame
from family_hub.ui.theme import is_dark

Refresh = Callable[[], Awaitable[None]]
ReadingCallback = Callable[[ReadingWrite], Awaitable[bool]]

i18n.register(
    {
        "fever.data.episodes": ("Fieberepisoden", "Fever episodes"),
        "fever.data.readings": ("Messungen", "Readings"),
        "fever.title": ("Fieber", "Fever"),
        "fever.subtitle": ("Messungen und Fieberkurven", "Readings and fever curves"),
        "fever.add_reading": ("Messung hinzufügen", "Add reading"),
        "fever.reading_for": ("Messung für {name}", "Reading for {name}"),
        "fever.new_episode": ("Neue Episode", "New episode"),
        "fever.new_episode_for": ("Neue Episode für {name}", "New episode for {name}"),
        "fever.default_label": ("Fieber {date}", "Fever {date}"),
        "fever.label": ("Bezeichnung", "Label"),
        "fever.episodes": ("Episoden", "Episodes"),
        "fever.no_episodes": ("Keine Episoden", "No episodes"),
        "fever.readings": ("Messungen", "Readings"),
        "fever.no_readings": ("Noch keine Messungen.", "No readings yet."),
        "fever.reading_count": ("{n} Messungen", "{n} readings"),
        "fever.since": ("seit {date}", "since {date}"),
        "fever.open": ("offen", "open"),
        "fever.max": ("max. {value} °C", "max {value} °C"),
        "fever.temperature": ("Temperatur", "Temperature"),
        "fever.method_optional": ("Messart (optional)", "Method (optional)"),
        "fever.saved": ("{value} °C gespeichert", "{value} °C saved"),
        "fever.not_found": ("Episode nicht gefunden.", "Episode not found."),
        "fever.to_overview": ("Zur Übersicht", "To overview"),
        "fever.edit_episode": ("Episode bearbeiten", "Edit episode"),
        "fever.download_csv": ("CSV herunterladen", "Download CSV"),
        "fever.close_episode": ("Episode beenden", "End episode"),
        "fever.reopen_episode": ("Wieder öffnen", "Reopen"),
        "fever.confirm_delete_episode": (
            "Episode „{label}“ mit allen Messungen löschen?",
            "Delete episode “{label}” with all readings?",
        ),
        "fever.confirm_delete_reading": ("Messung {value} °C löschen?", "Delete reading {value} °C?"),
        "fever.thresholds": (
            "Schwellen ({group}): erhöht ab {elevated} °C, Fieber ab {fever} °C",
            "Thresholds ({group}): elevated from {elevated} °C, fever from {fever} °C",
        ),
        "fever.curve": ("Fieberkurve", "Fever curve"),
        "fever.interpolation": ("Interpolation", "Interpolation"),
        "fever.group_by_day": ("Nach Tag", "By day"),
        "fever.last": ("Zuletzt", "Last"),
        "fever.highest": ("Höchstwert", "Highest"),
        "fever.duration": ("Dauer", "Duration"),
        "fever.days": ("{n} Tage", "{n} days"),
        "fever.level.normal": ("normal", "normal"),
        "fever.level.elevated": ("erhöht", "elevated"),
        "fever.level.fever": ("Fieber", "fever"),
        "fever.age_group.infant": ("Säugling", "Infant"),
        "fever.age_group.child": ("Kind", "Child"),
        "fever.age_group.adult": ("Erwachsen", "Adult"),
        "fever.method.ear": ("Ohr", "Ear"),
        "fever.method.rectal": ("Rektal", "Rectal"),
        "fever.method.forehead": ("Stirn", "Forehead"),
        "fever.method.armpit": ("Achsel", "Armpit"),
        "fever.method.oral": ("Mund", "Mouth"),
    }
)


def register_pages() -> None:
    """Register the fever pages."""

    @ui.page("/fever")
    async def overview_page() -> None:
        with frame("fever"):
            page_title(t("fever.title"), t("fever.subtitle"))
            await _overview()

    @ui.page("/fever/episodes/{episode_id}")
    async def episode_page(episode_id: int) -> None:
        with frame("fever"):
            await _episode_view(episode_id)


def _local(value: datetime) -> datetime:
    return value.astimezone(service.local_timezone())


def _temperature(value: float) -> str:
    return f"{i18n.number(value)} °C"


def _period(episode: EpisodeRead) -> str:
    start = i18n.day(_local(episode.started_at))
    if episode.ended_at is None:
        return t("fever.since", date=start)
    return f"{start} – {i18n.day(_local(episode.ended_at))}"


def reading_form(on_submit: ReadingCallback) -> None:
    """Temperature slider, date, time, method and note, as in the earlier fever app."""
    now = datetime.now(service.local_timezone())
    with ui.column().classes("w-full gap-3"):
        with ui.row().classes("w-full justify-between items-end"):
            ui.label(t("fever.temperature")).classes("text-sm hub-muted")
            value_label = ui.label(_temperature(37.0)).classes("text-3xl font-semibold hub-accent")
        slider = ui.slider(min=35.0, max=42.0, step=0.1, value=37.0).props("label color=primary").classes("w-full")
        slider.on_value_change(lambda e: value_label.set_text(_temperature(e.value)))
        with ui.row().classes("w-full gap-3 no-wrap"):
            date_input = DateField(t("common.date"), now.date())
            time_input = TimeField(t("common.time"), now.time().replace(second=0, microsecond=0))
        method = (
            ui.select(
                {m.value: t(f"fever.method.{m.value}") for m in Method},
                label=t("fever.method_optional"),
                clearable=True,
            )
            .props("outlined dense")
            .classes("w-full")
        )
        note = ui.input(t("common.note_optional")).props("outlined dense").classes("w-full")

        async def submit() -> None:
            measured_at = datetime.combine(date_input.value or now.date(), time_input.value)
            data = ReadingWrite(
                temperature=round(slider.value, 1),
                measured_at=measured_at,
                method=Method(method.value) if method.value else None,
                note=note.value or None,
            )
            if await on_submit(data):
                note.value = ""

        ui.button(t("fever.add_reading"), on_click=submit).props("unelevated").classes("w-full")


async def _quick_reading_dialog(person: PersonRead, on_saved: Refresh) -> None:
    with ui.dialog() as dialog, ui.card().classes("hub-card w-96 max-w-full p-5 gap-3"):
        ui.label(t("fever.reading_for", name=person.name)).classes("text-lg font-semibold")

        async def save(data: ReadingWrite) -> bool:
            quick = QuickReadingWrite(
                person_id=person.id,
                temperature=data.temperature,
                measured_at=data.measured_at,
                method=data.method,
                note=data.note,
            )
            try:
                async with db.session() as session:
                    await service.quick_add_reading(session, quick)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return False
            ui.notify(t("fever.saved", value=i18n.number(data.temperature)), type="positive")
            dialog.close()
            await on_saved()
            return True

        reading_form(save)
    dialog.open()


async def _new_episode_dialog(person: PersonRead) -> None:
    today = i18n.day(datetime.now(service.local_timezone()))
    with ui.dialog() as dialog, ui.card().classes("hub-card w-96 max-w-full p-5 gap-3"):
        ui.label(t("fever.new_episode_for", name=person.name)).classes("text-lg font-semibold")
        label = (
            ui.input(t("fever.label"), value=t("fever.default_label", date=today)).props("outlined").classes("w-full")
        )
        description = ui.input(t("common.description_optional")).props("outlined").classes("w-full")

        async def save() -> None:
            try:
                async with db.session() as session:
                    episode = await service.create_episode(
                        session, EpisodeWrite(person_id=person.id, label=label.value, description=description.value)
                    )
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            dialog.close()
            ui.navigate.to(f"/fever/episodes/{episode.id}")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.create"), on_click=save).props("unelevated")
    dialog.open()


def _episode_row(episode: EpisodeRead) -> None:
    is_open = episode.ended_at is None
    with (
        ui.row()
        .classes("w-full items-center gap-3 no-wrap p-2 rounded-lg cursor-pointer hover:bg-black/5")
        .on("click", lambda: ui.navigate.to(f"/fever/episodes/{episode.id}"))
    ):
        person_dot("#ef4444" if is_open else "var(--hub-border)")
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(episode.label).classes("font-medium truncate")
            ui.label(f"{_period(episode)} · {t('fever.reading_count', n=episode.reading_count)}").classes(
                "text-xs hub-muted"
            )
        if episode.last_reading and is_open:
            level_label(
                _temperature(episode.last_reading.temperature), episode.last_reading.level.value, "text-lg font-bold"
            )
        elif episode.max_temperature is not None:
            ui.label(t("fever.max", value=i18n.number(episode.max_temperature))).classes("text-sm hub-muted")


async def _overview() -> None:
    @ui.refreshable
    async def content() -> None:
        async with db.session() as session:
            people = await core_service.list_people(session)
            episodes = await service.list_episodes(session)
        if not people:
            with section():
                empty_state(t("core.empty"), t("common.manage_people"), lambda: ui.navigate.to("/people"))
            return
        people.sort(key=lambda p: (p.kind is not PersonKind.CHILD, p.name))
        with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2"):
            for person in people:
                own = [e for e in episodes if e.person_id == person.id]
                with ui.card().classes("hub-card p-4 gap-2").style(f"border-top: 4px solid {person.color}"):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.label(person.name).classes("text-lg font-semibold grow")
                        ui.button(icon="add_chart", on_click=lambda p=person: _new_episode_dialog(p)).props(
                            "flat round"
                        ).tooltip(t("fever.new_episode"))
                        ui.button(
                            t("fever.add_reading"),
                            on_click=lambda p=person: _quick_reading_dialog(p, content.refresh),
                        ).props("unelevated dense").classes("px-3")
                    if not own:
                        ui.label(t("fever.no_episodes")).classes("text-sm hub-muted")
                    for episode in own[:5]:
                        _episode_row(episode)

    await content()


async def _episode_view(episode_id: int) -> None:
    @ui.refreshable
    async def content() -> None:
        try:
            async with db.session() as session:
                detail = await service.get_episode(session, episode_id)
                person = await core_service.get_person(session, detail.episode.person_id)
        except service.NotFoundError:
            with section():
                empty_state(t("fever.not_found"), t("fever.to_overview"), lambda: ui.navigate.to("/fever"))
            return
        _episode_header(detail, person, content.refresh)
        _summary_tiles(detail)
        _chart_card(detail, content.refresh)

        async def add(data: ReadingWrite) -> bool:
            try:
                async with db.session() as session:
                    reading = await service.add_reading(session, episode_id, data)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return False
            ui.notify(t("fever.saved", value=i18n.number(reading.temperature)), type="positive")
            await content.refresh()
            return True

        with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2"):
            with section(t("fever.add_reading")):
                reading_form(add)
            _readings_card(detail, content.refresh)

    await content()


def _episode_header(detail: EpisodeDetail, person: PersonRead, refresh: Refresh) -> None:
    episode = detail.episode
    thresholds = episode.thresholds

    async def toggle_closed() -> None:
        async with db.session() as session:
            await service.set_closed(session, episode.id, closed=episode.ended_at is None)
        await refresh()

    async def remove() -> None:
        if not await confirm(t("fever.confirm_delete_episode", label=episode.label)):
            return
        async with db.session() as session:
            await service.delete_episode(session, episode.id)
        ui.navigate.to("/fever")

    def download() -> None:
        ui.download.content(service.readings_csv(detail), f"{episode.label}.csv", "text/csv")

    with ui.row().classes("w-full items-center gap-2 no-wrap"):
        ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/fever")).props("flat round")
        ui.element("div").classes("rounded-full").style(
            f"background:{person.color}; width:12px; height:44px; min-width:12px"
        )
        with ui.column().classes("gap-0 grow min-w-0"):
            ui.label(episode.label).classes("text-2xl font-bold truncate")
            ui.label(f"{person.name} · {_period(episode)}").classes("text-sm hub-muted truncate")
        with ui.button(icon="more_vert").props("flat round"), ui.menu():
            ui.menu_item(t("common.edit"), on_click=lambda: _edit_dialog(episode, refresh))
            ui.menu_item(t("fever.download_csv"), on_click=download)
            ui.menu_item(
                t("fever.close_episode") if episode.ended_at is None else t("fever.reopen_episode"),
                on_click=toggle_closed,
            )
            ui.separator()
            ui.menu_item(t("common.delete"), on_click=remove).classes("text-negative")
    if episode.description:
        ui.label(episode.description).classes("hub-muted")
    ui.label(
        t(
            "fever.thresholds",
            group=t(f"fever.age_group.{thresholds.age_group.value}"),
            elevated=i18n.number(thresholds.elevated),
            fever=i18n.number(thresholds.fever),
        )
    ).classes("text-xs hub-muted")


def _summary_tiles(detail: EpisodeDetail) -> None:
    if not detail.readings:
        return
    last = detail.readings[-1]
    highest = max(detail.readings, key=lambda r: r.temperature)
    start = detail.readings[0].measured_at
    end = detail.episode.ended_at or datetime.now(service.local_timezone())
    with ui.row().classes("w-full gap-3"):
        for label, reading in ((t("fever.last"), last), (t("fever.highest"), highest)):
            with ui.card().classes("p-3 gap-0 hub-card hub-tile"):
                ui.label(label).classes("text-xs uppercase tracking-wide hub-muted")
                level_label(_temperature(reading.temperature), reading.level.value, "text-2xl font-bold")
                ui.label(f"{i18n.short_day(_local(reading.measured_at))} {_local(reading.measured_at):%H:%M}").classes(
                    "text-xs hub-muted"
                )
        with ui.card().classes("p-3 gap-0 hub-card hub-tile"):
            ui.label(t("fever.duration")).classes("text-xs uppercase tracking-wide hub-muted")
            ui.label(t("fever.days", n=max((end - start).days, 0) + 1)).classes("text-2xl font-bold")
            ui.label(t("fever.reading_count", n=len(detail.readings))).classes("text-xs hub-muted")


def _edit_dialog(episode: EpisodeRead, refresh: Refresh) -> None:
    with ui.dialog() as dialog, ui.card().classes("hub-card w-96 max-w-full p-5 gap-3"):
        ui.label(t("fever.edit_episode")).classes("text-lg font-semibold")
        label = ui.input(t("fever.label"), value=episode.label).props("outlined").classes("w-full")
        description = (
            ui.input(t("common.description_optional"), value=episode.description or "")
            .props("outlined")
            .classes("w-full")
        )

        async def save() -> None:
            try:
                async with db.session() as session:
                    await service.update_episode(
                        session, episode.id, EpisodeUpdate(label=label.value, description=description.value)
                    )
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            dialog.close()
            await refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.save"), on_click=save).props("unelevated")
    dialog.open()


def _chart_card(detail: EpisodeDetail, refresh: Refresh) -> None:
    if not detail.readings:
        return
    interpolation = Interpolation(app.storage.user.get("fever_interpolation", Interpolation.PCHIP.value))

    async def change(event: object) -> None:
        app.storage.user["fever_interpolation"] = getattr(event, "value", Interpolation.PCHIP.value)
        await refresh()

    figure = fever_chart(
        detail.readings,
        detail.episode.thresholds,
        tz=service.local_timezone(),
        interpolation=interpolation,
        dark=is_dark(),
        labels=(t("fever.level.fever"), t("fever.level.elevated"), f"{t('fever.temperature')} (°C)"),
        day_format=i18n.short_day_format(),
    )
    with section(t("fever.curve")) as header:
        with header:
            ui.select(
                {i.value: label for i, label in INTERPOLATION_LABELS.items()},
                value=interpolation.value,
                on_change=change,
            ).props("outlined dense options-dense").classes("w-32").tooltip(t("fever.interpolation"))
        plot(figure)


def _readings_card(detail: EpisodeDetail, refresh: Refresh) -> None:
    group_by_date = app.storage.user.get("fever_group_by_date", True)

    async def toggle(event: object) -> None:
        app.storage.user["fever_group_by_date"] = bool(getattr(event, "value", True))
        await refresh()

    async def remove(reading: ReadingRead) -> None:
        if not await confirm(t("fever.confirm_delete_reading", value=i18n.number(reading.temperature))):
            return
        async with db.session() as session:
            await service.delete_reading(session, reading.id)
        await refresh()

    readings = sorted(detail.readings, key=lambda r: r.measured_at, reverse=True)
    with section(t("fever.readings")) as header:
        with header:
            ui.switch(t("fever.group_by_day"), value=group_by_date, on_change=toggle).props("dense")
        if not readings:
            empty_state(t("fever.no_readings"))
            return
        if not group_by_date:
            for reading in readings:
                _reading_row(reading, remove, show_date=True)
            return
        for day, day_readings in groupby(readings, key=lambda r: _local(r.measured_at).date()):
            items = list(day_readings)
            day_divider(f"{i18n.weekday(day.weekday())} · {i18n.day(day)}", len(items))
            for reading in items:
                _reading_row(reading, remove, show_date=False)


def _reading_row(reading: ReadingRead, on_delete: Callable[[ReadingRead], Awaitable[None]], *, show_date: bool) -> None:
    local = _local(reading.measured_at)
    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        level_label(_temperature(reading.temperature), reading.level.value, "font-bold text-lg w-20")
        with ui.column().classes("gap-0 grow min-w-0"):
            when = f"{i18n.day(local)} {local:%H:%M}" if show_date else f"{local:%H:%M}"
            extra = [t(f"fever.method.{reading.method.value}")] if reading.method else []
            ui.label(" · ".join([when, *extra])).classes("text-sm hub-muted")
            if reading.note:
                ui.label(reading.note).classes("text-sm truncate")
        ui.button(icon="delete_outline", on_click=lambda: on_delete(reading)).props("flat round dense color=negative")
