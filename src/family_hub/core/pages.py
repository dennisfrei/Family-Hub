"""Admin page for people and children (`/people`)."""

from collections.abc import Awaitable, Callable
from datetime import date

from nicegui import ui

from family_hub import db
from family_hub.core import service
from family_hub.core.models import DEFAULT_COLOR, PersonKind, Sex
from family_hub.core.schemas import PersonRead, PersonWrite
from family_hub.ui import i18n
from family_hub.ui.components import empty_state, page_title, section
from family_hub.ui.fields import DateField
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame

Refresh = Callable[[], Awaitable[None] | None]

i18n.register(
    {
        "core.title": ("Personen", "People"),
        "core.subtitle": ("Familie, Kinder und Betreuung", "Family, children and caregivers"),
        "core.add": ("Person hinzufügen", "Add person"),
        "core.new": ("Neue Person", "New person"),
        "core.edit": ("Person bearbeiten", "Edit person"),
        "core.empty": ("Noch keine Personen angelegt.", "No people yet."),
        "core.kind.adult": ("Erwachsen", "Adult"),
        "core.kind.child": ("Kind", "Child"),
        "core.sex.female": ("Mädchen", "Girl"),
        "core.sex.male": ("Junge", "Boy"),
        "core.birth_date": ("Geburtsdatum", "Birth date"),
        "core.sex": ("Geschlecht", "Sex"),
        "core.deactivate": ("Deaktivieren", "Deactivate"),
        "core.activate": ("Aktivieren", "Activate"),
        "core.inactive": ("inaktiv", "inactive"),
        "core.children": ("Kinder", "Children"),
        "core.adults": ("Erwachsene", "Adults"),
    }
)


def register_pages() -> None:
    """Register the people admin page."""

    @ui.page("/people")
    async def people_page() -> None:
        with frame("core"):
            with page_title(t("core.title"), t("core.subtitle")):
                ui.button(t("core.add"), on_click=lambda: person_dialog(None, people_list.refresh)).props(
                    "unelevated rounded"
                )

            @ui.refreshable
            async def people_list() -> None:
                async with db.session() as session:
                    people = await service.list_people(session, include_inactive=True)
                if not people:
                    with section():
                        empty_state(t("core.empty"))
                    return
                for kind, title in ((PersonKind.CHILD, t("core.children")), (PersonKind.ADULT, t("core.adults"))):
                    group = [p for p in people if p.kind is kind]
                    if not group:
                        continue
                    with section(title), ui.column().classes("w-full gap-2"):
                        for person in group:
                            _person_row(person, people_list.refresh)

            await people_list()


def _person_row(person: PersonRead, on_saved: Refresh) -> None:
    with ui.row().classes("w-full items-center gap-3 no-wrap py-1"):
        with (
            ui.element("div")
            .classes("rounded-full flex items-center justify-center text-white font-bold")
            .style(
                f"background:{person.color}; width:40px; height:40px; min-width:40px; opacity:{1 if person.active else 0.4}"
            )
        ):
            ui.label(person.name[:1].upper())
        with ui.column().classes("gap-0 grow min-w-0"):
            name = ui.label(person.name).classes("text-base font-medium truncate")
            if not person.active:
                name.classes("line-through hub-muted")
            details = [t(f"core.kind.{person.kind.value}")]
            if person.birth_date and person.sex:
                age = i18n.format_age(service.age_in_months(person.birth_date, date.today()))
                details += [t(f"core.sex.{person.sex.value}"), i18n.day(person.birth_date), age]
            if not person.active:
                details.append(t("core.inactive"))
            ui.label(" · ".join(details)).classes("text-sm hub-muted truncate")
        ui.button(icon="edit", on_click=lambda: person_dialog(person, on_saved)).props("flat round").tooltip(
            t("common.edit")
        )
        ui.button(
            icon="person_off" if person.active else "person",
            on_click=lambda: _toggle_active(person, on_saved),
        ).props("flat round").tooltip(t("core.deactivate") if person.active else t("core.activate"))


async def _call(callback: Refresh) -> None:
    result = callback()
    if result is not None:
        await result


async def _toggle_active(person: PersonRead, on_saved: Refresh) -> None:
    async with db.session() as session:
        await service.set_active(session, person.id, active=not person.active)
    await _call(on_saved)


def person_dialog(person: PersonRead | None, on_saved: Refresh, *, default_kind: PersonKind = PersonKind.CHILD) -> None:
    """Dialog to add a person (of `default_kind` initially) or edit one."""
    with ui.dialog() as dialog, ui.card().classes("hub-card w-96 max-w-full p-5 gap-3"):
        ui.label(t("core.edit") if person else t("core.new")).classes("text-lg font-semibold")
        name = (
            ui.input(t("common.name"), value=person.name if person else "")
            .props("outlined")
            .classes("w-full")
            .mark("person-name")
        )
        kind = ui.toggle(
            {k.value: t(f"core.kind.{k.value}") for k in PersonKind},
            value=(person.kind if person else default_kind).value,
        ).props("unelevated")
        color = (
            ui.color_input(t("common.color"), value=person.color if person else DEFAULT_COLOR)
            .props("outlined")
            .classes("w-full")
        )
        with ui.column().classes("w-full gap-3").bind_visibility_from(kind, "value", value=PersonKind.CHILD.value):
            birth_date = DateField(t("core.birth_date"), person.birth_date if person else None)
            sex = (
                ui.select(
                    {s.value: t(f"core.sex.{s.value}") for s in Sex},
                    label=t("core.sex"),
                    value=person.sex.value if person and person.sex else None,
                )
                .props("outlined")
                .classes("w-full")
            )

        async def save() -> None:
            is_child = kind.value == PersonKind.CHILD.value
            born = birth_date.value if is_child else None
            data = PersonWrite(
                name=name.value or "",
                kind=PersonKind(kind.value),
                color=color.value or DEFAULT_COLOR,
                birth_date=born,
                sex=Sex(sex.value) if is_child and sex.value else None,
            )
            try:
                async with db.session() as session:
                    if person is None:
                        await service.create_person(session, data)
                    else:
                        await service.update_person(session, person.id, data)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            dialog.close()
            await _call(on_saved)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.save"), on_click=save).props("unelevated")
    dialog.open()
