"""Time capsule page (`/time-capsule`): quick capture, timeline with filters, milestones, on this day, export."""

from collections.abc import Awaitable, Callable
from datetime import date
from itertools import groupby

from nicegui import app, ui

from family_hub import db
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.schemas import ChildRead, PersonRead
from family_hub.errors import InvalidInputError
from family_hub.time_capsule import export, service
from family_hub.time_capsule.models import EntryType
from family_hub.time_capsule.schemas import EntryFilter, EntryRead, EntryWrite
from family_hub.ui import i18n
from family_hub.ui.components import empty_state, page_title, person_chip, person_dot, section
from family_hub.ui.dialogs import confirm
from family_hub.ui.fields import DateField
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame

Refresh = Callable[[], Awaitable[None]]

TYPE_COLORS = {EntryType.SAYING: "#2563eb", EntryType.MOMENT: "#64748b", EntryType.MILESTONE: "#d97706"}
FILTER_KEY = "tc_filter"
AUTHOR_KEY = "tc_author"

i18n.register(
    {
        "tc.data.entries": ("Einträge nur über diese Person", "Entries only about this person"),
        "tc.data.shared": (
            "Gemeinsame Einträge (bleiben für die anderen Kinder)",
            "Shared entries (kept for the other children)",
        ),
        "tc.title": ("Zeitkapsel", "Time capsule"),
        "tc.subtitle": ("Sprüche, Momente und Meilensteine", "Sayings, moments and milestones"),
        "tc.type.saying": ("Spruch", "Saying"),
        "tc.type.moment": ("Moment", "Moment"),
        "tc.type.milestone": ("Meilenstein", "Milestone"),
        "tc.capture": ("Festhalten", "Capture"),
        "tc.placeholder": ("Was ist passiert, was wurde gesagt?", "What happened, what was said?"),
        "tc.more": ("Datum, Kontext, Tags", "Date, context, tags"),
        "tc.context": ("Kontext (optional)", "Context (optional)"),
        "tc.context_hint": ("z. B. beim Frühstück, als es regnete", "e.g. at breakfast when it rained"),
        "tc.tags": ("Tags", "Tags"),
        "tc.author": ("Ich bin", "I am"),
        "tc.saved": ("Gespeichert", "Saved"),
        "tc.choose_child": ("Mindestens ein Kind auswählen", "Choose at least one child"),
        "tc.tab.timeline": ("Zeitstrahl", "Timeline"),
        "tc.tab.milestones": ("Meilensteine", "Milestones"),
        "tc.tab.on_this_day": ("An diesem Tag", "On this day"),
        "tc.tab.export": ("Export", "Export"),
        "tc.filter.child": ("Kind", "Child"),
        "tc.filter.type": ("Art", "Type"),
        "tc.filter.tag": ("Tag", "Tag"),
        "tc.filter.year": ("Jahr", "Year"),
        "tc.filter.reset": ("Filter zurücksetzen", "Reset filters"),
        "tc.empty": (
            "Noch keine Einträge. Halte oben den ersten Moment fest!",
            "No entries yet. Capture the first moment above!",
        ),
        "tc.no_results": ("Keine Einträge für diese Filter.", "No entries for these filters."),
        "tc.no_milestones": ("Noch keine Meilensteine.", "No milestones yet."),
        "tc.no_on_this_day": (
            "Heute vor einem oder mehr Jahren wurde nichts festgehalten.",
            "Nothing was captured on this day in earlier years.",
        ),
        "tc.years_ago": ("vor {n} Jahren", "{n} years ago"),
        "tc.year_ago": ("vor einem Jahr", "one year ago"),
        "tc.edit": ("Eintrag bearbeiten", "Edit entry"),
        "tc.confirm_delete": ("Diesen Eintrag löschen?", "Delete this entry?"),
        "tc.by": ("von {name}", "by {name}"),
        "tc.booklet": ("Jahresheft (PDF)", "Yearly booklet (PDF)"),
        "tc.booklet_hint": (
            "Ein Heft pro Kind und Jahr, z. B. als Geschenk für die Großeltern.",
            "One booklet per child and year, e.g. as a gift for grandparents.",
        ),
        "tc.booklet_count": ("{n} Einträge", "{n} entries"),
        "tc.data_export": ("Datenexport", "Data export"),
        "tc.data_export_hint": (
            "Alle Einträge, damit die Daten nie von der App abhängen.",
            "All entries, so the data never depends on the app.",
        ),
        "tc.markdown": ("Markdown", "Markdown"),
        "tc.json": ("JSON", "JSON"),
        "tc.entries": ("{n} Einträge", "{n} entries"),
    }
)


def register_pages() -> None:
    """Register the time capsule page."""

    @ui.page("/time-capsule")
    async def time_capsule_page() -> None:
        with frame("time_capsule"):
            page_title(t("tc.title"), t("tc.subtitle"))
            await _content()


async def _load_people() -> tuple[list[ChildRead], dict[int, PersonRead]]:
    async with db.session() as session:
        children = await core_service.list_children(session)
        people = {p.id: p for p in await core_service.list_people(session, include_inactive=True)}
    return children, people


async def _content() -> None:
    children, people = await _load_people()
    if not children:
        with section():
            empty_state(t("common.no_children"), t("common.manage_people"), lambda: ui.navigate.to("/people"))
        return

    @ui.refreshable
    async def timeline() -> None:
        await _timeline(children, people, timeline.refresh)

    _capture_card(children, people, timeline.refresh)
    with (
        ui.tabs()
        .props(
            "dense no-caps inline-label active-color=primary indicator-color=primary align=left mobile-arrows outside-arrows"
        )
        .classes("w-full") as tabs
    ):
        tab_timeline = ui.tab("timeline", t("tc.tab.timeline"))
        tab_milestones = ui.tab("milestones", t("tc.tab.milestones"))
        tab_today = ui.tab("today", t("tc.tab.on_this_day"))
        tab_export = ui.tab("export", t("tc.tab.export"))
    with ui.tab_panels(tabs, value=tab_timeline).classes("w-full bg-transparent"):
        with ui.tab_panel(tab_timeline).classes("p-0 gap-4"):
            await timeline()
        with ui.tab_panel(tab_milestones).classes("p-0 gap-4"):
            await _milestones(children)
        with ui.tab_panel(tab_today).classes("p-0 gap-4"):
            await _on_this_day(people, timeline.refresh)
        with ui.tab_panel(tab_export).classes("p-0 gap-4"):
            await _export_panel(children)


def _child_toggles(children: list[ChildRead], selected: set[int]) -> None:
    @ui.refreshable
    def chips() -> None:
        with ui.row().classes("gap-2"):
            for child in children:
                person_chip(
                    child.name, child.color, selected=child.id in selected, on_click=lambda c=child: toggle(c.id)
                )

    def toggle(child_id: int) -> None:
        selected.symmetric_difference_update({child_id})
        chips.refresh()

    chips()


class _EntryForm:
    """The shared entry form (capture card and edit dialog)."""

    def __init__(self, children: list[ChildRead], people: dict[int, PersonRead], entry: EntryRead | None) -> None:
        self.selected = (
            {c.person_id for c in entry.children} if entry else ({children[0].id} if len(children) == 1 else set())
        )
        self.text = (
            ui.textarea(placeholder=t("tc.placeholder"), value=entry.text if entry else "")
            .props("outlined autogrow input-style='min-height: 4.5rem; font-size: 1.1rem'")
            .classes("w-full")
        )
        _child_toggles(children, self.selected)
        self.entry_type = ui.toggle(
            {k.value: t(f"tc.type.{k.value}") for k in EntryType},
            value=(entry.type if entry else EntryType.MOMENT).value,
        ).props("unelevated no-caps toggle-color=primary")
        with (
            ui.expansion(t("tc.more"), value=entry is not None).classes("w-full").props("dense"),
            ui.column().classes("w-full gap-3 pt-2"),
        ):
            self.day = DateField(t("common.date"), entry.date if entry else date.today())
            self.context = (
                ui.input(t("tc.context"), placeholder=t("tc.context_hint"), value=entry.context if entry else "")
                .props("outlined dense")
                .classes("w-full")
            )
            self.tags = (
                ui.input_chips(t("tc.tags"), value=list(entry.tags) if entry else [], new_value_mode="add-unique")
                .props("outlined dense")
                .classes("w-full")
            )
            adults = {p.id: p.name for p in people.values() if p.kind is PersonKind.ADULT and p.active}
            self.author = (
                ui.select(adults, label=t("tc.author"), value=app.storage.user.get(AUTHOR_KEY), clearable=True)
                .props("outlined dense")
                .classes("w-full")
            )
            self.author.on_value_change(lambda e: app.storage.user.update({AUTHOR_KEY: e.value}))

    def read(self) -> EntryWrite:
        """Return the form content.

        Raises:
            InvalidInputError: If no child is selected.
        """
        entry_day = self.day.value or date.today()
        if not self.selected:
            raise InvalidInputError("error.child_required")
        return EntryWrite(
            text=self.text.value or "",
            person_ids=sorted(self.selected),
            type=EntryType(self.entry_type.value),
            date=entry_day,
            context=self.context.value or None,
            tags=list(self.tags.value or []),
            author_id=self.author.value,
        )

    def reset(self) -> None:
        """Clear text, context and tags after saving."""
        self.text.set_value("")
        self.context.set_value("")
        self.tags.set_value([])


def _capture_card(children: list[ChildRead], people: dict[int, PersonRead], refresh: Refresh) -> None:
    with section(t("tc.capture")):
        form = _EntryForm(children, people, None)

        async def save() -> None:
            try:
                data = form.read()
                async with db.session() as session:
                    await service.create_entry(session, data)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            form.reset()
            ui.notify(t("tc.saved"), type="positive")
            await refresh()

        ui.button(t("common.save"), on_click=save).props("unelevated size=lg").classes("w-full")


def _edit_dialog(entry: EntryRead, children: list[ChildRead], people: dict[int, PersonRead], refresh: Refresh) -> None:
    with ui.dialog() as dialog, ui.card().classes("hub-card w-[32rem] max-w-full p-5 gap-3"):
        ui.label(t("tc.edit")).classes("text-lg font-semibold")
        form = _EntryForm(children, people, entry)

        async def save() -> None:
            try:
                data = form.read()
                async with db.session() as session:
                    await service.update_entry(session, entry.id, data)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            dialog.close()
            await refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.save"), on_click=save).props("unelevated")
    dialog.open()


def entry_card(
    entry: EntryRead,
    *,
    children: list[ChildRead] | None = None,
    people: dict[int, PersonRead] | None = None,
    refresh: Refresh | None = None,
    caption: str | None = None,
) -> None:
    """One entry; with `refresh` it gets edit and delete actions."""
    color = TYPE_COLORS[entry.type]
    with ui.card().classes("hub-card w-full p-4 gap-2").style(f"border-left: 3px solid {color}"):
        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            ui.label(t(f"tc.type.{entry.type.value}")).classes("text-xs font-medium").style(f"color:{color}")
            ui.label(caption or f"{i18n.weekday_short(entry.date.weekday())}, {i18n.day(entry.date)}").classes(
                "text-xs hub-muted grow"
            )
            if refresh is not None and children is not None and people is not None:

                async def remove() -> None:
                    if not await confirm(t("tc.confirm_delete")):
                        return
                    async with db.session() as session:
                        await service.delete_entry(session, entry.id)
                    await refresh()

                with ui.button(icon="more_vert").props("flat round dense"), ui.menu():
                    ui.menu_item(t("common.edit"), on_click=lambda: _edit_dialog(entry, children, people, refresh))
                    ui.menu_item(t("common.delete"), on_click=remove).classes("text-negative")
        if entry.type is EntryType.SAYING:
            ui.label(f"„{entry.text}“" if i18n.language() is i18n.Language.DE else f"“{entry.text}”").classes(
                "text-xl italic font-medium leading-snug whitespace-pre-line"
            )
        else:
            ui.label(entry.text).classes(
                "text-base whitespace-pre-line" + (" font-semibold" if entry.type is EntryType.MILESTONE else "")
            )
        if entry.context:
            ui.label(entry.context).classes("text-sm hub-muted italic")
        with ui.row().classes("items-center gap-2"):
            for child in entry.children:
                age = f" · {i18n.format_age(child.age_months)}" if child.age_months is not None else ""
                with ui.row().classes("items-center gap-1 no-wrap"):
                    person_dot(child.color, 8)
                    ui.label(f"{child.name}{age}").classes("text-xs font-medium")
            for tag in entry.tags:
                ui.label(f"#{tag}").classes("text-xs hub-muted")
            if entry.author_name:
                ui.label(t("tc.by", name=entry.author_name)).classes("text-xs hub-muted ml-auto")


def _current_filter() -> EntryFilter:
    stored = app.storage.user.get(FILTER_KEY, {})
    return EntryFilter(
        person_id=stored.get("person_id"),
        type=EntryType(stored["type"]) if stored.get("type") else None,
        tag=stored.get("tag"),
        year=stored.get("year"),
        query=stored.get("query"),
    )


async def _timeline(children: list[ChildRead], people: dict[int, PersonRead], refresh: Refresh) -> None:
    filters = _current_filter()
    filtered = any((filters.person_id, filters.type, filters.tag, filters.year, filters.query))
    async with db.session() as session:
        entries = await service.list_entries(session, filters)
        tags = await service.list_tags(session)
        years = await service.years(session)

    async def update(key: str, value: object) -> None:
        stored = dict(app.storage.user.get(FILTER_KEY, {}))
        stored[key] = value or None
        app.storage.user[FILTER_KEY] = stored
        await refresh()

    async def reset() -> None:
        app.storage.user[FILTER_KEY] = {}
        await refresh()

    with ui.row().classes("w-full items-center gap-2"):
        ui.select(
            {c.id: c.name for c in children},
            label=t("tc.filter.child"),
            value=filters.person_id,
            clearable=True,
            on_change=lambda e: update("person_id", e.value),
        ).props("outlined dense").classes("w-36")
        ui.select(
            {k.value: t(f"tc.type.{k.value}") for k in EntryType},
            label=t("tc.filter.type"),
            value=filters.type.value if filters.type else None,
            clearable=True,
            on_change=lambda e: update("type", e.value),
        ).props("outlined dense").classes("w-36")
        ui.select(
            {tag.name: f"#{tag.name} ({tag.count})" for tag in tags},
            label=t("tc.filter.tag"),
            value=filters.tag,
            clearable=True,
            on_change=lambda e: update("tag", e.value),
        ).props("outlined dense").classes("w-36")
        ui.select(
            years,
            label=t("tc.filter.year"),
            value=filters.year,
            clearable=True,
            on_change=lambda e: update("year", e.value),
        ).props("outlined dense").classes("w-28")
        ui.input(placeholder=t("common.search"), value=filters.query or "").props(
            "outlined dense clearable debounce=400"
        ).classes("grow min-w-40").on("update:model-value", lambda e: update("query", e.args)).props(
            "prepend-inner-icon=search"
        )
        if filtered:
            ui.button(icon="filter_alt_off", on_click=reset).props("flat round").tooltip(t("tc.filter.reset"))

    if not entries:
        with section():
            empty_state(t("tc.no_results") if filtered else t("tc.empty"))
        return
    ui.label(t("tc.entries", n=len(entries))).classes("text-xs hub-muted")
    for _, month_entries in groupby(entries, key=lambda e: (e.date.year, e.date.month)):
        items = list(month_entries)
        ui.label(i18n.month_year(items[0].date)).classes("text-lg font-bold mt-2")
        for entry in items:
            entry_card(entry, children=children, people=people, refresh=refresh)


async def _milestones(children: list[ChildRead]) -> None:
    async with db.session() as session:
        by_child = {child.id: await service.milestones(session, child.id) for child in children}
    if not any(by_child.values()):
        with section():
            empty_state(t("tc.no_milestones"))
        return
    with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2"):
        for child in children:
            with section(child.name) as header:
                header.style(f"border-bottom: 3px solid {child.color}; padding-bottom: 6px")
                if not by_child[child.id]:
                    ui.label(t("tc.no_milestones")).classes("text-sm hub-muted")
                for entry in by_child[child.id]:
                    age = next((c.age_months for c in entry.children if c.person_id == child.id), None)
                    with ui.row().classes("w-full items-start gap-3 no-wrap"):
                        ui.label(i18n.format_age(age) if age is not None else "").classes(
                            "text-sm font-semibold w-24 shrink-0 text-amber-500"
                        )
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(entry.text).classes("text-sm")
                            ui.label(i18n.day(entry.date)).classes("text-xs hub-muted")


async def _on_this_day(people: dict[int, PersonRead], refresh: Refresh) -> None:
    today = date.today()
    async with db.session() as session:
        entries = await service.on_this_day(session, today)
    if not entries:
        with section():
            empty_state(t("tc.no_on_this_day"))
        return
    for entry in entries:
        years = today.year - entry.date.year
        caption = t("tc.year_ago") if years == 1 else t("tc.years_ago", n=years)
        entry_card(entry, caption=f"{caption} · {i18n.day(entry.date)}")


async def _export_panel(children: list[ChildRead]) -> None:
    async with db.session() as session:
        years = await service.years(session) or [date.today().year]
    with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2"):
        with section(t("tc.booklet")):
            ui.label(t("tc.booklet_hint")).classes("text-sm hub-muted")
            child = (
                ui.select({c.id: c.name for c in children}, value=children[0].id, label=t("tc.filter.child"))
                .props("outlined dense")
                .classes("w-full")
            )
            year = ui.select(years, value=years[0], label=t("tc.filter.year")).props("outlined dense").classes("w-full")

            async def booklet() -> None:
                name = next(c.name for c in children if c.id == child.value)
                async with db.session() as session:
                    entries = await service.list_entries(session, EntryFilter(person_id=child.value, year=year.value))
                pdf = export.booklet_pdf(entries, name, year.value)
                ui.download.content(pdf, f"{t('tc.title')}-{name}-{year.value}.pdf", "application/pdf")

            ui.button(t("common.download"), on_click=booklet).props("unelevated")
        with section(t("tc.data_export")):
            ui.label(t("tc.data_export_hint")).classes("text-sm hub-muted")

            async def download(kind: str) -> None:
                async with db.session() as session:
                    entries = await service.list_entries(session)
                if kind == "json":
                    ui.download.content(export.to_json(entries), "zeitkapsel.json", "application/json")
                else:
                    ui.download.content(export.to_markdown(entries, t("tc.title")), "zeitkapsel.md", "text/markdown")

            with ui.row().classes("gap-2"):
                ui.button(t("tc.markdown"), on_click=lambda: download("md")).props("outline")
                ui.button(t("tc.json"), on_click=lambda: download("json")).props("outline")
