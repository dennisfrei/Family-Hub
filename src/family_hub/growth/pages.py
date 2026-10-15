"""Growth page (`/growth`): status tiles, charts, entry form and measurements per child."""

from collections.abc import Awaitable, Callable
from datetime import date
from itertools import groupby

from nicegui import app, ui

from family_hub import db
from family_hub.core import service as core_service
from family_hub.core.schemas import ChildRead, PersonRead
from family_hub.growth import report, service
from family_hub.growth.chart import TYPE_COLORS, growth_chart, sds_chart, type_label, velocity_chart
from family_hub.growth.metrics import age_months, growth_velocity
from family_hub.growth.models import UNITS, MeasurementType
from family_hub.growth.schemas import MeasurementRead, MeasurementWrite, TypeStatus
from family_hub.ui import i18n
from family_hub.ui.components import (
    day_divider,
    empty_state,
    page_title,
    person_chip,
    person_dot,
    plot,
    section,
    stat_tile,
)
from family_hub.ui.dialogs import confirm
from family_hub.ui.fields import DateField
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame
from family_hub.ui.theme import is_dark

Refresh = Callable[[], Awaitable[None]]

RECENT_DAYS = 5

i18n.register(
    {
        "growth.data.measurements": ("Wachstumsmessungen", "Growth measurements"),
        "growth.title": ("Wachstum", "Growth"),
        "growth.subtitle": ("Größe, Gewicht und Perzentilen", "Height, weight and percentiles"),
        "growth.type.weight": ("Gewicht", "Weight"),
        "growth.type.length": ("Größe", "Height"),
        "growth.type.head": ("Kopfumfang", "Head circumference"),
        "growth.age": ("Alter", "Age"),
        "growth.born": ("geb. {date}", "born {date}"),
        "growth.age_months": ("Alter (Monate)", "Age (months)"),
        "growth.age_years": ("Alter (Jahre)", "Age (years)"),
        "growth.measurement": ("Messung", "Measurement"),
        "growth.child": ("Kind", "Child"),
        "growth.child_on_p50": ("Kind auf P50", "Child on P50"),
        "growth.per_month": ("{unit}/Monat", "{unit}/month"),
        "growth.tab.percentiles": ("Perzentilen", "Percentiles"),
        "growth.tab.sds": ("SDS-Verlauf", "SDS course"),
        "growth.tab.velocity": ("Geschwindigkeit", "Velocity"),
        "growth.no_reference": (
            "Keine Referenzdaten für diesen Messtyp konfiguriert; Perzentilen werden nicht angezeigt.",
            "No reference data configured for this type; percentiles are not shown.",
        ),
        "growth.legend_official": (
            "Gefüllte Punkte: beim Arzt gemessen · Ringe: zu Hause · Fläche: P25–P75",
            "Filled dots: measured at the doctor's · rings: at home · band: P25–P75",
        ),
        "growth.sds_hint": (
            "Bleibt die Linie parallel zu einer Perzentile, wächst das Kind in seinem Kanal.",
            "A line parallel to a percentile means the child keeps its channel.",
        ),
        "growth.velocity_hint": (
            "Wachstum pro Monat, bis 2 Jahre monatlich, danach halbjährlich; Linie: Kind auf P50.",
            "Growth per month, monthly until 2 years, then half-yearly; line: child on P50.",
        ),
        "growth.no_data": ("Noch zu wenige Messungen.", "Not enough measurements yet."),
        "growth.new": ("Neue Messung", "New measurement"),
        "growth.at_doctor": ("Beim Arzt gemessen", "Measured at the doctor's"),
        "growth.at_doctor_short": ("beim Arzt", "at the doctor's"),
        "growth.at_home": ("zu Hause", "at home"),
        "growth.enter_value": ("Mindestens einen Wert eingeben", "Enter at least one value"),
        "growth.saved": ("{n} Messung(en) gespeichert", "{n} measurement(s) saved"),
        "growth.measurements": ("Messungen", "Measurements"),
        "growth.no_measurements": ("Noch keine Messungen.", "No measurements yet."),
        "growth.confirm_delete": ("{label} vom {date} löschen?", "Delete {label} from {date}?"),
        "growth.export": ("Export", "Export"),
        "growth.export_pdf": ("PDF-Bericht", "PDF report"),
        "growth.export_html": ("HTML-Bericht (interaktiv)", "HTML report (interactive)"),
        "growth.export_csv": ("CSV-Tabelle", "CSV table"),
        "growth.report.created": ("erstellt {date}", "created {date}"),
        "growth.report.reference": (
            "Referenz: {name}. Perzentilen und SDS nach der LMS-Methode berechnet.",
            "Reference: {name}. Percentiles and SDS calculated with the LMS method.",
        ),
        "growth.report.reference_unnamed": (
            "Perzentilen und SDS nach der LMS-Methode aus den konfigurierten Referenzdaten berechnet.",
            "Percentiles and SDS calculated with the LMS method from the configured reference data.",
        ),
        "growth.report.type": ("Art", "Type"),
        "growth.report.value": ("Wert", "Value"),
        "growth.report.unit": ("Einheit", "Unit"),
        "growth.report.percentile": ("Perzentile", "Percentile"),
        "growth.report.yes": ("ja", "yes"),
        "growth.report.no": ("nein", "no"),
        "growth.older": ("Ältere Messungen ({n} Tage)", "Older measurements ({n} days)"),
        "growth.since": ("{delta} seit {date}", "{delta} since {date}"),
    }
)


def register_pages() -> None:
    """Register the growth page."""

    @ui.page("/growth")
    async def growth_page() -> None:
        with frame("growth"):
            page_title(t("growth.title"), t("growth.subtitle"))
            await _content()


async def _content() -> None:
    @ui.refreshable
    async def content() -> None:
        async with db.session() as session:
            children = await core_service.list_children(session)
        if not children:
            with section():
                empty_state(t("common.no_children"), t("common.manage_people"), lambda: ui.navigate.to("/people"))
            return
        selected_id = app.storage.user.get("growth_child")
        child = next((c for c in children if c.id == selected_id), children[0])

        async def select_child(child_id: int) -> None:
            app.storage.user["growth_child"] = child_id
            await content.refresh()

        if len(children) > 1:
            with ui.row().classes("gap-2"):
                for option in children:
                    person_chip(
                        option.name,
                        option.color,
                        selected=option.id == child.id,
                        on_click=lambda c=option: select_child(c.id),
                    )

        async with db.session() as session:
            person = await core_service.get_person(session, child.id)
            measurements = await service.list_measurements(session, child.id)
            statuses = await service.status(session, child.id)

        _status_tiles(child, statuses)
        _chart_section(person, measurements, content.refresh)
        with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2"):
            _entry_form(child, content.refresh)
            _measurement_list(child, measurements, content.refresh)

    await content()


def _status_tiles(child: ChildRead, statuses: list[TypeStatus]) -> None:
    with ui.row().classes("w-full gap-3"):
        stat_tile(
            t("growth.age"),
            i18n.format_age(child.age_months),
            t("growth.born", date=i18n.day(child.birth_date)),
            accent=child.color,
        )
        for item in statuses:
            latest = item.latest
            details = []
            if latest.percentile is not None:
                details.append(f"P{latest.percentile:.0f}")
            if item.previous is not None:
                delta = f"{i18n.signed(latest.value - item.previous.value, 2)} {latest.unit}"
                details.append(t("growth.since", delta=delta, date=i18n.day(item.previous.measured_on)))
            else:
                details.append(i18n.day(latest.measured_on))
            stat_tile(
                type_label(item.type),
                f"{i18n.number(latest.value, 2)} {latest.unit}",
                " · ".join(details),
                accent=TYPE_COLORS[item.type],
            )


def _chart_section(person: PersonRead, measurements: list[MeasurementRead], refresh: Refresh) -> None:
    measurement_type = MeasurementType(app.storage.user.get("growth_type", MeasurementType.LENGTH.value))
    own = [m for m in measurements if m.type is measurement_type]
    reference = service.reference_for(person, measurement_type)
    age_now = age_months(person.birth_date, date.today()) if person.birth_date else 0.0
    dark = is_dark()

    async def select_type(event: object) -> None:
        app.storage.user["growth_type"] = getattr(event, "value", MeasurementType.LENGTH.value)
        await refresh()

    with section(toolbar=True) as header:
        with header:
            with (
                ui.tabs()
                .props("dense no-caps inline-label active-color=primary indicator-color=primary")
                .classes("grow") as tabs
            ):
                tab_percentiles = ui.tab("p", t("growth.tab.percentiles"))
                tab_sds = ui.tab("sds", t("growth.tab.sds"))
                tab_velocity = ui.tab("v", t("growth.tab.velocity"))
            ui.toggle(
                {m.value: type_label(m) for m in MeasurementType},
                value=measurement_type.value,
                on_change=select_type,
            ).props("unelevated dense no-caps toggle-color=primary")
        with ui.tab_panels(tabs, value=tab_percentiles).props("animated").classes("w-full bg-transparent"):
            with ui.tab_panel(tab_percentiles).classes("p-0"):
                if reference is None:
                    ui.label(t("growth.no_reference")).classes("text-sm hub-muted")
                plot(growth_chart(own, measurement_type, reference, age_now, dark=dark))
                ui.label(t("growth.legend_official")).classes("text-xs hub-muted")
            with ui.tab_panel(tab_sds).classes("p-0"):
                if any(m.z is not None for m in measurements):
                    plot(sds_chart(measurements, age_now, dark=dark))
                    ui.label(t("growth.sds_hint")).classes("text-xs hub-muted")
                else:
                    empty_state(t("growth.no_reference") if reference is None else t("growth.no_data"))
            with ui.tab_panel(tab_velocity).classes("p-0"):
                bins = growth_velocity(service.to_points(own), reference)
                if bins:
                    plot(velocity_chart(bins, measurement_type, dark=dark))
                    ui.label(t("growth.velocity_hint")).classes("text-xs hub-muted")
                else:
                    empty_state(t("growth.no_data"))


def _entry_form(child: ChildRead, refresh: Refresh) -> None:
    with section(t("growth.new")):
        measured_on = DateField(t("common.date"), date.today())
        inputs = {}
        for measurement_type in MeasurementType:
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                person_dot(TYPE_COLORS[measurement_type], 8)
                inputs[measurement_type] = (
                    ui.number(
                        f"{type_label(measurement_type)} ({UNITS[measurement_type]})",
                        format="%.2f",
                        step=0.1 if measurement_type is MeasurementType.WEIGHT else 0.5,
                    )
                    .props("outlined dense")
                    .classes("grow")
                )
        official = ui.switch(t("growth.at_doctor"), value=True).props("color=primary")
        note = ui.input(t("common.note_optional")).props("outlined dense").classes("w-full")

        async def save() -> None:
            day = measured_on.value or date.today()
            items = [
                MeasurementWrite(
                    person_id=child.id,
                    type=measurement_type,
                    value=float(field.value),
                    measured_on=day,
                    official=bool(official.value),
                    note=note.value or None,
                )
                for measurement_type, field in inputs.items()
                if field.value is not None
            ]
            if not items:
                ui.notify(t("growth.enter_value"), type="warning")
                return
            try:
                async with db.session() as session:
                    await service.add_measurements(session, items)
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            ui.notify(t("growth.saved", n=len(items)), type="positive")
            await refresh()

        ui.button(t("common.save"), on_click=save).props("unelevated").classes("w-full")


def _measurement_list(child: ChildRead, measurements: list[MeasurementRead], refresh: Refresh) -> None:
    async def remove(measurement: MeasurementRead) -> None:
        label = f"{type_label(measurement.type)} {i18n.number(measurement.value, 2)} {measurement.unit}"
        if not await confirm(t("growth.confirm_delete", label=label, date=i18n.day(measurement.measured_on))):
            return
        async with db.session() as session:
            await service.delete_measurement(session, measurement.id)
        await refresh()

    def day_rows(day: date, day_items: list[MeasurementRead]) -> None:
        day_divider(f"{i18n.day(day)} · {i18n.format_age(int(day_items[0].age_months))}")
        for measurement in day_items:
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                person_dot(TYPE_COLORS[measurement.type], 8)
                ui.label(type_label(measurement.type)).classes("text-sm grow min-w-0 truncate")
                ui.label(f"{i18n.number(measurement.value, 2)} {measurement.unit}").classes("font-semibold")
                if measurement.percentile is not None:
                    ui.label(f"P{measurement.percentile:.0f}").classes("text-xs hub-muted w-8 text-right")
                if not measurement.official:
                    ui.label(t("growth.at_home")).classes("text-xs hub-muted")
                ui.button(icon="delete_outline", on_click=lambda m=measurement: remove(m)).props(
                    "flat round dense color=negative"
                )

    async def download(kind: str) -> None:
        async with db.session() as session:
            data = await report.load(session, child.id)
        builders = {
            "pdf": (report.build_pdf, "application/pdf"),
            "html": (report.build_html, "text/html"),
            "csv": (report.build_csv, "text/csv"),
        }
        build, media_type = builders[kind]
        ui.download.content(build(data), f"{data.file_stem()}.{kind}", media_type)

    with section(t("growth.measurements")) as header:
        if measurements:
            with header, ui.button(t("growth.export")).props("flat dense no-caps"), ui.menu():
                ui.menu_item(t("growth.export_pdf"), on_click=lambda: download("pdf"))
                ui.menu_item(t("growth.export_html"), on_click=lambda: download("html"))
                ui.menu_item(t("growth.export_csv"), on_click=lambda: download("csv"))
        if not measurements:
            empty_state(t("growth.no_measurements"))
            return
        newest_first = sorted(measurements, key=lambda m: (m.measured_on, m.id), reverse=True)
        days = [(day, list(items)) for day, items in groupby(newest_first, key=lambda m: m.measured_on)]
        for day, day_items in days[:RECENT_DAYS]:
            day_rows(day, day_items)
        if len(days) > RECENT_DAYS:
            with ui.expansion(t("growth.older", n=len(days) - RECENT_DAYS)).classes("w-full").props("dense"):
                for day, day_items in days[RECENT_DAYS:]:
                    day_rows(day, day_items)
