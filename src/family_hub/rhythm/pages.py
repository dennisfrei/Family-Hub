"""Rhythm pages: week view with swaps, duties and rules, stats (`/rhythm`) and print view (`/rhythm/print`)."""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from html import escape

from nicegui import app, ui
from pydantic import BaseModel, ConfigDict

from family_hub import db
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.schemas import PersonRead
from family_hub.rhythm import service
from family_hub.rhythm.logic import DAYS_PER_WEEK, Source, week_start
from family_hub.rhythm.models import DEFAULT_COLOR, RotationPeriod, RuleMode, TimeOfDay
from family_hub.rhythm.schemas import DayRead, DutyRead, DutyWrite, RuleWrite, SlotRead
from family_hub.ui import i18n
from family_hub.ui.components import empty_state, page_title, person_dot, section
from family_hub.ui.dialogs import confirm
from family_hub.ui.fields import DateField
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame
from family_hub.ui.theme import apply_theme

Refresh = Callable[[], Awaitable[None]]

ICON_CHOICES = [
    "task_alt",
    "wb_sunny",
    "breakfast_dining",
    "directions_walk",
    "child_care",
    "school",
    "pool",
    "sports_soccer",
    "bathtub",
    "bedtime",
    "restaurant",
    "local_grocery_store",
    "cleaning_services",
    "pets",
    "directions_car",
    "elderly",
    "work",
    "music_note",
]
NO_RULE = "none"

i18n.register(
    {
        "rhythm.data.duties": ("Dienste nur für diese Person", "Duties only for this person"),
        "rhythm.data.rules": (
            "Regeln mit dieser Person (wird offen bzw. aus der Rotation genommen)",
            "Rules with this person (become open or drop the person from the rotation)",
        ),
        "rhythm.data.swaps": ("Einmalige Tausche", "One-off swaps"),
        "rhythm.title": ("Takt", "Rhythm"),
        "rhythm.subtitle": ("Wer macht was diese Woche", "Who does what this week"),
        "rhythm.tab.week": ("Woche", "Week"),
        "rhythm.tab.duties": ("Dienste", "Duties"),
        "rhythm.tab.stats": ("Statistik", "Stats"),
        "rhythm.this_week": ("Diese Woche", "This week"),
        "rhythm.next_week": ("Nächste Woche", "Next week"),
        "rhythm.week_of": ("Woche {range}", "Week {range}"),
        "rhythm.print": ("Drucken", "Print"),
        "rhythm.open": ("offen", "open"),
        "rhythm.swapped": ("getauscht", "swapped"),
        "rhythm.warning": ("Regel verweist auf inaktive Personen", "Rule points to inactive people"),
        "rhythm.time.morning": ("Morgens", "Morning"),
        "rhythm.time.afternoon": ("Nachmittags", "Afternoon"),
        "rhythm.time.evening": ("Abends", "Evening"),
        "rhythm.no_duties": ("Noch keine Dienste.", "No duties yet."),
        "rhythm.add_duty": ("Dienst hinzufügen", "Add duty"),
        "rhythm.new_duty": ("Neuer Dienst", "New duty"),
        "rhythm.edit_duty": ("Dienst bearbeiten", "Edit duty"),
        "rhythm.time_of_day": ("Tageszeit", "Time of day"),
        "rhythm.weekdays": ("Wochentage", "Weekdays"),
        "rhythm.icon": ("Symbol", "Icon"),
        "rhythm.for_child": ("Für Kind (optional)", "For child (optional)"),
        "rhythm.rules": ("Regeln", "Rules"),
        "rhythm.rules_for": ("Regeln: {name}", "Rules: {name}"),
        "rhythm.mode.none": ("Keine Regel", "No rule"),
        "rhythm.mode.fixed": ("Fest", "Fixed"),
        "rhythm.mode.rotation": ("Wechselnd", "Rotation"),
        "rhythm.person": ("Person", "Person"),
        "rhythm.rotation_people": ("Reihenfolge", "Order"),
        "rhythm.period.daily": ("täglich", "daily"),
        "rhythm.period.weekly": ("wöchentlich", "weekly"),
        "rhythm.anchor": ("Start", "Start"),
        "rhythm.copy_first": ("Erste Zeile für alle Tage übernehmen", "Copy first row to all days"),
        "rhythm.preset": ("Vorlage", "Preset"),
        "rhythm.inactive": ("inaktiv", "inactive"),
        "rhythm.deactivate": ("Deaktivieren", "Deactivate"),
        "rhythm.activate": ("Aktivieren", "Activate"),
        "rhythm.confirm_delete": ("Dienst „{name}“ löschen?", "Delete duty “{name}”?"),
        "rhythm.swap_title": ("{duty} am {day}", "{duty} on {day}"),
        "rhythm.swap_hint": ("Nur für diesen Tag ändern", "Change for this day only"),
        "rhythm.restore_rule": ("Regel wiederherstellen", "Restore rule"),
        "rhythm.no_rule_summary": ("ohne Regel", "no rule"),
        "rhythm.rotation_summary": ("{names} ({period})", "{names} ({period})"),
        "rhythm.stats_title": ("Wer hat wie oft?", "Who did how often?"),
        "rhythm.stats_hint": (
            "Gezählt wird der Plan inklusive Tausch, bis heute.",
            "Counts the plan including swaps, up to today.",
        ),
        "rhythm.period_4w": ("4 Wochen", "4 weeks"),
        "rhythm.period_3m": ("3 Monate", "3 months"),
        "rhythm.period_12m": ("12 Monate", "12 months"),
        "rhythm.total": ("Alle Dienste", "All duties"),
        "rhythm.no_stats": ("Noch keine zugewiesenen Dienste.", "No assigned duties yet."),
        "rhythm.no_adults": ("Lege zuerst Erwachsene unter Personen an.", "Add adults under People first."),
        "rhythm.today": ("Heute", "Today"),
    }
)


def register_pages() -> None:
    """Register the rhythm pages."""

    @ui.page("/rhythm")
    async def rhythm_page() -> None:
        with frame("rhythm", wide=True):
            page_title(t("rhythm.title"), t("rhythm.subtitle"))
            await _content()

    @ui.page("/rhythm/print")
    async def print_page(week: str = "current") -> None:
        await _print_view(week)


async def _people(*, include_inactive: bool = True) -> dict[int, PersonRead]:
    async with db.session() as session:
        return {p.id: p for p in await core_service.list_people(session, include_inactive=include_inactive)}


def _assignable(people: dict[int, PersonRead]) -> dict[int, str]:
    return {p.id: p.name for p in people.values() if p.active and p.kind is PersonKind.ADULT}


async def _content() -> None:
    with (
        ui.tabs()
        .props(
            "dense no-caps inline-label active-color=primary indicator-color=primary align=left mobile-arrows outside-arrows"
        )
        .classes("w-full") as tabs
    ):
        tab_week = ui.tab("week", t("rhythm.tab.week"))
        tab_duties = ui.tab("duties", t("rhythm.tab.duties"))
        tab_stats = ui.tab("stats", t("rhythm.tab.stats"))
    with (
        ui.tab_panels(tabs, value=app.storage.user.get("rhythm_tab", "week"))
        .classes("w-full bg-transparent")
        .on_value_change(lambda e: app.storage.user.update(rhythm_tab=e.value))
    ):
        with ui.tab_panel(tab_week).classes("p-0 gap-4"):
            await _week_panel()
        with ui.tab_panel(tab_duties).classes("p-0 gap-4"):
            await _duties_panel()
        with ui.tab_panel(tab_stats).classes("p-0 gap-4"):
            await _stats_panel()


def _selected_start() -> date:
    offset = 1 if app.storage.user.get("rhythm_next_week", False) else 0
    return week_start(date.today()) + timedelta(days=offset * DAYS_PER_WEEK)


async def _week_panel() -> None:
    @ui.refreshable
    async def content() -> None:
        start = _selected_start()
        people = await _people()
        async with db.session() as session:
            week = await service.week(session, start)
            duties = await service.list_duties(session)

        async def switch(event: object) -> None:
            app.storage.user["rhythm_next_week"] = getattr(event, "value", "current") == "next"
            await content.refresh()

        with ui.row().classes("w-full items-center gap-2"):
            ui.toggle(
                {"current": t("rhythm.this_week"), "next": t("rhythm.next_week")},
                value="next" if app.storage.user.get("rhythm_next_week", False) else "current",
                on_change=switch,
            ).props("unelevated no-caps toggle-color=primary")
            ui.label(t("rhythm.week_of", range=i18n.day_range(start, start + timedelta(days=6)))).classes(
                "text-sm hub-muted grow"
            )
            week_param = "next" if app.storage.user.get("rhythm_next_week", False) else "current"
            ui.button(
                t("rhythm.print"),
                on_click=lambda: ui.navigate.to(f"/rhythm/print?week={week_param}", new_tab=True),
            ).props("flat no-caps")
        if not duties:
            with section():
                empty_state(t("rhythm.no_duties"))
            return
        with ui.element("div").classes("w-full grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-7"):
            for day in week.days:
                _day_card(day, people, content.refresh)
        _legend(people, week.days)

    await content()


def _day_card(day: DayRead, people: dict[int, PersonRead], refresh: Refresh) -> None:
    is_today = day.date == date.today()
    card = ui.card().classes("hub-card p-3 gap-2")
    if is_today:
        card.style("border: 2px solid var(--q-primary)")
    with card:
        with ui.row().classes("w-full items-baseline gap-2 no-wrap"):
            ui.label(i18n.weekday_short(day.date.weekday())).classes("text-lg font-bold")
            ui.label(i18n.short_day(day.date)).classes("text-sm hub-muted grow")
            if is_today:
                ui.label(t("rhythm.today")).classes("text-xs hub-accent font-medium")
        for time_of_day in TimeOfDay:
            slots = [slot for slot in day.slots if slot.time_of_day is time_of_day]
            if not slots:
                continue
            ui.label(t(f"rhythm.time.{time_of_day.value}")).classes("text-xs hub-muted mt-1")
            for slot in slots:
                _slot_chip(slot, people, refresh)


def _slot_chip(slot: SlotRead, people: dict[int, PersonRead], refresh: Refresh) -> None:
    person = people.get(slot.person_id) if slot.person_id is not None else None
    border = f"4px solid {person.color}" if person else "4px dashed var(--hub-muted)"
    with (
        ui.element("div")
        .classes("w-full rounded-md px-2 py-1 cursor-pointer")
        .style(f"border-left: {border}; background: var(--hub-bg)")
        .on("click", lambda: _swap_dialog(slot, people, refresh))
    ):
        with ui.row().classes("items-center gap-1 no-wrap"):
            ui.label(slot.duty_name).classes("text-sm font-medium leading-tight grow break-words min-w-0").style(
                "hyphens: auto"
            )
            if slot.source is Source.SWAP:
                ui.icon("swap_horiz").classes("text-sm hub-muted").tooltip(t("rhythm.swapped"))
            if slot.warning:
                ui.icon("warning").classes("text-sm text-orange-500").tooltip(t("rhythm.warning"))
        name = person.name if person else t("rhythm.open")
        child = people.get(slot.for_person_id) if slot.for_person_id else None
        ui.label(f"{name} · {child.name}" if child else name).classes("text-xs " + ("" if person else "hub-muted"))


def _legend(people: dict[int, PersonRead], days: list[DayRead]) -> None:
    used = {slot.person_id for day in days for slot in day.slots if slot.person_id is not None}
    with ui.row().classes("gap-3"):
        for person_id in used:
            person = people.get(person_id)
            if person:
                with ui.row().classes("items-center gap-1"):
                    ui.element("div").classes("rounded-full").style(
                        f"background:{person.color}; width:12px; height:12px"
                    )
                    ui.label(person.name).classes("text-sm hub-muted")


def _swap_dialog(slot: SlotRead, people: dict[int, PersonRead], refresh: Refresh) -> None:
    first, last = service.swap_window(date.today())
    if not first <= slot.date <= last:
        return
    options = _assignable(people)
    with ui.dialog() as dialog, ui.card().classes("hub-card w-80 max-w-full p-5 gap-3"):
        ui.label(
            t(
                "rhythm.swap_title",
                duty=slot.duty_name,
                day=f"{i18n.weekday(slot.date.weekday())}, {i18n.short_day(slot.date)}",
            )
        ).classes("text-lg font-semibold")
        ui.label(t("rhythm.swap_hint")).classes("text-sm hub-muted")
        if not options:
            ui.label(t("rhythm.no_adults")).classes("text-sm")

        async def choose(person_id: int) -> None:
            async with db.session() as session:
                await service.set_swap(session, slot.duty_id, slot.date, person_id)
            dialog.close()
            await refresh()

        async def restore() -> None:
            async with db.session() as session:
                await service.remove_swap(session, slot.duty_id, slot.date)
            dialog.close()
            await refresh()

        with ui.column().classes("w-full gap-2"):
            for person_id, name in options.items():
                person = people[person_id]
                ui.button(name, on_click=lambda pid=person_id: choose(pid)).props("unelevated no-caps").style(
                    f"background:{person.color} !important; color:white"
                ).classes("w-full")
        if slot.source is Source.SWAP:
            ui.button(t("rhythm.restore_rule"), on_click=restore).props("flat no-caps")
        ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
    dialog.open()


def _rule_summary(duty: DutyRead, people: dict[int, PersonRead]) -> str:
    parts = []
    for weekday in duty.weekdays:
        rule = next((r for r in duty.rules if r.weekday == weekday), None)
        if rule is None:
            text = t("rhythm.no_rule_summary")
        elif rule.mode is RuleMode.FIXED:
            text = people[rule.person_id].name if rule.person_id in people else "?"
        else:
            names = "/".join(people[p].name for p in rule.rotation_person_ids if p in people)
            period = t(f"rhythm.period.{(rule.rotation_period or RotationPeriod.WEEKLY).value}")
            text = t("rhythm.rotation_summary", names=names, period=period)
        parts.append(f"{i18n.weekday_short(weekday)}: {text}")
    return " · ".join(parts)


async def _duties_panel() -> None:
    @ui.refreshable
    async def content() -> None:
        people = await _people()
        async with db.session() as session:
            duties = await service.list_duties(session, include_inactive=True)
        with section(t("rhythm.tab.duties")) as header:
            with header:
                ui.button(t("rhythm.add_duty"), on_click=lambda: _duty_dialog(None, people, content.refresh)).props(
                    "unelevated rounded no-caps"
                )
            if not duties:
                empty_state(t("rhythm.no_duties"))
            for index, duty in enumerate(duties):
                _duty_row(duty, people, content.refresh, first=index == 0, last=index == len(duties) - 1)

    await content()


def _duty_row(duty: DutyRead, people: dict[int, PersonRead], refresh: Refresh, *, first: bool, last: bool) -> None:
    async def move(offset: int) -> None:
        async with db.session() as session:
            await service.move_duty(session, duty.id, offset)
        await refresh()

    async def toggle_active() -> None:
        async with db.session() as session:
            await service.set_active(session, duty.id, active=not duty.active)
        await refresh()

    async def remove() -> None:
        if not await confirm(t("rhythm.confirm_delete", name=duty.name)):
            return
        async with db.session() as session:
            await service.delete_duty(session, duty.id)
        await refresh()

    with (
        ui.row()
        .classes("w-full items-center gap-3 no-wrap py-2")
        .style(f"border-left: 5px solid {duty.color}; padding-left: 10px; opacity: {1 if duty.active else 0.5}")
    ):
        ui.icon(duty.icon).classes("text-2xl")
        with ui.column().classes("gap-0 grow min-w-0"):
            with ui.row().classes("items-center gap-2"):
                ui.label(duty.name).classes("font-semibold")
                ui.label(t(f"rhythm.time.{duty.time_of_day.value}")).classes("text-xs hub-muted")
                if duty.is_preset:
                    ui.badge(t("rhythm.preset")).props("outline color=primary")
                if not duty.active:
                    ui.badge(t("rhythm.inactive")).props("outline color=grey")
            ui.label(_rule_summary(duty, people)).classes("text-xs hub-muted")
        ui.button(icon="arrow_upward", on_click=lambda: move(-1)).props("flat round dense").set_enabled(not first)
        ui.button(icon="arrow_downward", on_click=lambda: move(1)).props("flat round dense").set_enabled(not last)
        with ui.button(icon="more_vert").props("flat round dense"), ui.menu():
            ui.menu_item(t("rhythm.rules"), on_click=lambda: _rules_dialog(duty, people, refresh))
            ui.menu_item(t("common.edit"), on_click=lambda: _duty_dialog(duty, people, refresh))
            ui.menu_item(t("rhythm.deactivate") if duty.active else t("rhythm.activate"), on_click=toggle_active)
            ui.separator()
            ui.menu_item(t("common.delete"), on_click=remove).classes("text-negative")


def _duty_dialog(duty: DutyRead | None, people: dict[int, PersonRead], refresh: Refresh) -> None:
    children = {p.id: p.name for p in people.values() if p.kind is PersonKind.CHILD and p.active}
    with ui.dialog() as dialog, ui.card().classes("hub-card w-96 max-w-full p-5 gap-3"):
        ui.label(t("rhythm.edit_duty") if duty else t("rhythm.new_duty")).classes("text-lg font-semibold")
        name = ui.input(t("common.name"), value=duty.name if duty else "").props("outlined").classes("w-full")
        time_of_day = ui.toggle(
            {time.value: t(f"rhythm.time.{time.value}") for time in TimeOfDay},
            value=(duty.time_of_day if duty else TimeOfDay.MORNING).value,
        ).props("unelevated no-caps toggle-color=primary")
        ui.label(t("rhythm.weekdays")).classes("text-sm hub-muted")
        weekdays = (
            ui.select(
                {day: i18n.weekday_short(day) for day in range(DAYS_PER_WEEK)},
                value=duty.weekdays if duty else list(range(5)),
                multiple=True,
            )
            .props("outlined dense use-chips")
            .classes("w-full")
        )
        icon = (
            ui.select(
                {name: name for name in ICON_CHOICES},
                value=duty.icon if duty else ICON_CHOICES[0],
                label=t("rhythm.icon"),
            )
            .props("outlined dense")
            .classes("w-full")
        )
        icon.add_slot(
            "option",
            r"""<q-item v-bind="props.itemProps"><q-item-section avatar><q-icon :name="props.opt.value" /></q-item-section>
            <q-item-section>{{ props.opt.label }}</q-item-section></q-item>""",
        )
        color = (
            ui.color_input(t("common.color"), value=duty.color if duty else DEFAULT_COLOR)
            .props("outlined dense")
            .classes("w-full")
        )
        for_person = (
            ui.select(children, value=duty.for_person_id if duty else None, label=t("rhythm.for_child"), clearable=True)
            .props("outlined dense")
            .classes("w-full")
        )

        async def save() -> None:
            data = DutyWrite(
                name=name.value or "",
                time_of_day=TimeOfDay(time_of_day.value),
                weekdays=sorted(weekdays.value or []),
                icon=icon.value or ICON_CHOICES[0],
                color=color.value or DEFAULT_COLOR,
                for_person_id=for_person.value,
            )
            try:
                async with db.session() as session:
                    if duty is None:
                        await service.create_duty(session, data)
                    else:
                        await service.update_duty(session, duty.id, data)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            dialog.close()
            await refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.save"), on_click=save).props("unelevated")
    dialog.open()


class _RuleRow(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    mode: ui.select
    person: ui.select
    rotation: ui.select
    period: ui.select
    anchor: DateField

    def copy_from(self, other: "_RuleRow") -> None:
        self.mode.value = other.mode.value
        self.person.value = other.person.value
        self.rotation.value = other.rotation.value
        self.period.value = other.period.value
        self.anchor.value = other.anchor.value

    def to_rule(self, weekday: int) -> RuleWrite:
        return RuleWrite(
            weekday=weekday,
            mode=RuleMode(self.mode.value),
            person_id=self.person.value,
            rotation_person_ids=list(self.rotation.value or []),
            rotation_period=RotationPeriod(self.period.value),
            anchor_date=self.anchor.value,
        )


def _rules_dialog(duty: DutyRead, people: dict[int, PersonRead], refresh: Refresh) -> None:
    options = _assignable(people)
    rows: dict[int, _RuleRow] = {}
    with ui.dialog() as dialog, ui.card().classes("hub-card w-[44rem] max-w-full p-5 gap-3"):
        ui.label(t("rhythm.rules_for", name=duty.name)).classes("text-lg font-semibold")
        if not options:
            ui.label(t("rhythm.no_adults")).classes("text-sm")
        for weekday in duty.weekdays:
            rule = next((r for r in duty.rules if r.weekday == weekday), None)
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(i18n.weekday_short(weekday)).classes("w-8 font-semibold")
                mode = (
                    ui.select(
                        {NO_RULE: t("rhythm.mode.none"), **{m.value: t(f"rhythm.mode.{m.value}") for m in RuleMode}},
                        value=rule.mode.value if rule else NO_RULE,
                    )
                    .props("outlined dense")
                    .classes("w-32")
                )
                person = (
                    ui.select(options, value=rule.person_id if rule else None, label=t("rhythm.person"))
                    .props("outlined dense")
                    .classes("w-40")
                )
                person.bind_visibility_from(mode, "value", value=RuleMode.FIXED.value)
                rotation = (
                    ui.select(
                        options,
                        value=rule.rotation_person_ids if rule else [],
                        multiple=True,
                        label=t("rhythm.rotation_people"),
                    )
                    .props("outlined dense use-chips")
                    .classes("w-56")
                )
                period = (
                    ui.select(
                        {p.value: t(f"rhythm.period.{p.value}") for p in RotationPeriod},
                        value=(rule.rotation_period if rule and rule.rotation_period else RotationPeriod.WEEKLY).value,
                    )
                    .props("outlined dense")
                    .classes("w-32")
                )
                anchor = DateField(
                    t("rhythm.anchor"),
                    rule.anchor_date if rule and rule.anchor_date else week_start(date.today()),
                ).classes("w-40")
                for element in (rotation, period, anchor.input):
                    element.bind_visibility_from(mode, "value", value=RuleMode.ROTATION.value)
                rows[weekday] = _RuleRow(mode=mode, person=person, rotation=rotation, period=period, anchor=anchor)

        def copy_first() -> None:
            if not rows:
                return
            first = rows[duty.weekdays[0]]
            for row in rows.values():
                row.copy_from(first)

        async def save() -> None:
            rules = [row.to_rule(weekday) for weekday, row in rows.items() if row.mode.value != NO_RULE]
            try:
                async with db.session() as session:
                    await service.set_rules(session, duty.id, rules)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            dialog.close()
            await refresh()

        with ui.row().classes("w-full items-center gap-2"):
            ui.button(t("rhythm.copy_first"), on_click=copy_first).props("flat no-caps")
            ui.space()
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.save"), on_click=save).props("unelevated")
    dialog.open()


STAT_PERIODS = {"4w": 28, "3m": 91, "12m": 365}


def _share_bar(counts: dict[int, int], open_count: int, people: dict[int, PersonRead]) -> None:
    total = sum(counts.values()) + open_count
    with (
        ui.element("div")
        .classes("w-full flex rounded overflow-hidden")
        .style("height: 12px; background: var(--hub-border)")
    ):
        for person_id, count in sorted(counts.items(), key=lambda item: -item[1]):
            person = people.get(person_id)
            color = person.color if person else "var(--hub-muted)"
            ui.element("div").style(f"width:{100 * count / total:.2f}%; background:{color}")
    with ui.row().classes("w-full gap-x-4 gap-y-0"):
        for person_id, count in sorted(counts.items(), key=lambda item: -item[1]):
            person = people.get(person_id)
            with ui.row().classes("items-center gap-1 no-wrap"):
                person_dot(person.color if person else "var(--hub-muted)", 8)
                ui.label(f"{person.name if person else '?'} {count} ({100 * count / total:.0f} %)").classes("text-sm")
        if open_count:
            ui.label(f"{t('rhythm.open')} {open_count}").classes("text-sm hub-muted")


async def _stats_panel() -> None:
    @ui.refreshable
    async def content() -> None:
        period = app.storage.user.get("rhythm_stats_period", "4w")
        today = date.today()
        people = await _people()
        async with db.session() as session:
            stats = await service.duty_stats(session, today - timedelta(days=STAT_PERIODS[period] - 1), today)

        async def switch(event: object) -> None:
            app.storage.user["rhythm_stats_period"] = getattr(event, "value", "4w")
            await content.refresh()

        with section(t("rhythm.stats_title")) as header:
            with header:
                ui.toggle(
                    {key: t(f"rhythm.period_{key}") for key in STAT_PERIODS},
                    value=period,
                    on_change=switch,
                ).props("unelevated no-caps dense toggle-color=primary")
            ui.label(t("rhythm.stats_hint")).classes("text-xs hub-muted")
            if not any(stat.counts for stat in stats):
                empty_state(t("rhythm.no_stats"))
                return
            totals: dict[int, int] = {}
            for stat in stats:
                for person_id, count in stat.counts.items():
                    totals[person_id] = totals.get(person_id, 0) + count
            ui.label(t("rhythm.total")).classes("font-semibold mt-2")
            _share_bar(totals, 0, people)
            for stat in stats:
                with ui.column().classes("w-full gap-1 mt-3"):
                    with ui.row().classes("items-center gap-2"):
                        person_dot(stat.color, 8)
                        ui.label(stat.duty_name).classes("font-medium")
                    _share_bar(stat.counts, stat.open, people)

    await content()


async def _print_view(week: str) -> None:
    apply_theme()
    ui.dark_mode(False)
    ui.add_css(
        "@page { size: A4 landscape; margin: 10mm; } .print-table td, .print-table th { border: 1px solid #cbd5e1; }"
    )
    start = week_start(date.today()) + timedelta(days=DAYS_PER_WEEK if week == "next" else 0)
    people = await _people()
    async with db.session() as session:
        schedule = await service.week(session, start)
    with ui.column().classes("w-full p-4 gap-3 bg-white text-black"):
        with ui.row().classes("w-full items-center"):
            ui.label(
                f"{t('rhythm.title')} · {t('rhythm.week_of', range=i18n.day_range(start, start + timedelta(days=6)))}"
            ).classes("text-2xl font-bold grow")
            ui.button(t("rhythm.print"), on_click=lambda: ui.run_javascript("window.print()")).props(
                "unelevated no-caps"
            ).classes("no-print")
        rows = "".join(
            "<tr><th class='p-2 text-left align-top' style='width:9%'>"
            + t(f"rhythm.time.{time.value}")
            + "</th>"
            + "".join(
                "<td class='p-2 align-top' style='width:13%'>"
                + "".join(
                    f"<div style='border-left:4px solid {slot.color}; padding-left:6px; margin-bottom:6px'>"
                    f"<div style='font-weight:600'>{escape(slot.duty_name)}</div>"
                    f"<div style='color:{people[slot.person_id].color if slot.person_id in people else '#64748b'}'>"
                    f"{escape(people[slot.person_id].name) if slot.person_id in people else '—'}</div></div>"
                    for slot in day.slots
                    if slot.time_of_day is time
                )
                + "</td>"
                for day in schedule.days
            )
            + "</tr>"
            for time in TimeOfDay
        )
        header = "".join(
            f"<th class='p-2'>{i18n.weekday(day.date.weekday())}<br><span style='font-weight:400'>{i18n.short_day(day.date)}</span></th>"
            for day in schedule.days
        )
        ui.html(
            f"<table class='print-table w-full' style='border-collapse:collapse; font-size:14px'>"
            f"<thead><tr><th></th>{header}</tr></thead><tbody>{rows}</tbody></table>",
            sanitize=False,
        ).classes("w-full")
