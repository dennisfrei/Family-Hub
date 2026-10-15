"""Start page (`/`): today across all modules; reads other modules only through their services."""

from datetime import date, datetime

from nicegui import app, ui

from family_hub import db
from family_hub.config import get_settings
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.pages import person_dialog
from family_hub.fever import service as fever_service
from family_hub.home.onboarding import SetupStep, StepKey, is_complete, load_state, setup_steps
from family_hub.rhythm import service as rhythm_service
from family_hub.rhythm.models import TimeOfDay
from family_hub.time_capsule import service as time_capsule_service
from family_hub.ui import i18n
from family_hub.ui.components import empty_state, level_label, person_dot, section
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame

i18n.register(
    {
        "home.title": ("Home", "Home"),
        "home.greeting.morning": ("Guten Morgen", "Good morning"),
        "home.greeting.day": ("Hallo", "Hello"),
        "home.greeting.evening": ("Guten Abend", "Good evening"),
        "home.today": ("{weekday}, {date}", "{weekday}, {date}"),
        "home.duties_today": ("Heute im Takt", "Today's duties"),
        "home.no_duties": ("Heute keine Dienste geplant.", "No duties planned today."),
        "home.sick": ("Gerade krank", "Currently sick"),
        "home.last_reading": ("zuletzt {time}", "last {time}"),
        "home.on_this_day": ("An diesem Tag", "On this day"),
        "home.years_ago": ("vor {n} Jahr(en)", "{n} year(s) ago"),
        "home.children": ("Kinder", "Children"),
        "home.quick": ("Schnellzugriff", "Quick actions"),
        "home.new_reading": ("Fieber messen", "Take temperature"),
        "home.new_memory": ("Moment festhalten", "Capture a moment"),
        "home.new_measurement": ("Größe & Gewicht", "Height & weight"),
        "home.week": ("Wochenplan", "Weekly plan"),
        "home.setup.title": ("Willkommen bei Family Hub", "Welcome to Family Hub"),
        "home.setup.intro": (
            "Ein paar Schritte, dann ist alles bereit. Abgehakt wird automatisch.",
            "A few steps and everything is ready. Steps are ticked off automatically.",
        ),
        "home.setup.hide": ("Ausblenden", "Hide"),
        "home.setup.optional": ("optional", "optional"),
        "home.setup.adults": ("Erwachsene anlegen", "Add adults"),
        "home.setup.adults.detail": (
            "Wer sich um die Kinder kümmert; für Takt und Zeitkapsel.",
            "Who looks after the children; for duties and the time capsule.",
        ),
        "home.setup.adults.action": ("Erwachsene Person hinzufügen", "Add adult"),
        "home.setup.children": ("Kinder anlegen", "Add children"),
        "home.setup.children.detail": (
            "Mit Geburtsdatum und Geschlecht; für Fieber, Wachstum und Zeitkapsel.",
            "With birth date and sex; for fever, growth and the time capsule.",
        ),
        "home.setup.children.action": ("Kind hinzufügen", "Add child"),
        "home.setup.rhythm": ("Takt einrichten", "Set up duties"),
        "home.setup.rhythm.detail": (
            "Festlegen, wer an welchem Wochentag bringt, abholt und ins Bett bringt.",
            "Decide who takes, picks up and puts to bed on which weekday.",
        ),
        "home.setup.rhythm.action": ("Zum Takt", "Go to duties"),
        "home.setup.reference": ("Wachstums-Referenz", "Growth reference"),
        "home.setup.reference.detail": (
            "Für Perzentilen und SDS: Referenztabellen über GROWTH_REFERENCE_DIR einbinden (siehe README).",
            "For percentiles and SDS: provide reference tables via GROWTH_REFERENCE_DIR (see README).",
        ),
        "home.setup.backup": ("Backups", "Backups"),
        "home.setup.backup.detail": (
            "S3-Ziel über BACKUP_BUCKET einrichten; Status und Sicherung unter Verwaltung.",
            "Configure an S3 target via BACKUP_BUCKET; status and backups under Admin.",
        ),
    }
)

GREETING_HOURS = (11, 18)
DISMISSED_KEY = "onboarding_dismissed"


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < GREETING_HOURS[0]:
        return t("home.greeting.morning")
    if hour < GREETING_HOURS[1]:
        return t("home.greeting.day")
    return t("home.greeting.evening")


def _hide_onboarding() -> None:
    app.storage.general[DISMISSED_KEY] = True
    ui.navigate.reload()


def _open_duties() -> None:
    app.storage.user["rhythm_tab"] = "duties"
    ui.navigate.to("/rhythm")


def _step_action(step: SetupStep) -> None:
    actions = {
        StepKey.ADULTS: lambda: person_dialog(None, ui.navigate.reload, default_kind=PersonKind.ADULT),
        StepKey.CHILDREN: lambda: person_dialog(None, ui.navigate.reload, default_kind=PersonKind.CHILD),
        StepKey.RHYTHM: _open_duties,
    }
    action = actions.get(step.key)
    if action is not None and not step.done:
        ui.button(t(f"home.setup.{step.key.value}.action"), on_click=action).props("outline no-caps").classes(
            "self-start"
        )


def _onboarding(steps: list[SetupStep]) -> None:
    with section(t("home.setup.title")) as header:
        with header:
            ui.button(t("home.setup.hide"), on_click=_hide_onboarding).props("flat dense no-caps")
        ui.label(t("home.setup.intro")).classes("text-sm hub-muted")
        for step in steps:
            with ui.row().classes("w-full no-wrap items-start gap-3 py-1"):
                ui.icon("check_circle" if step.done else "radio_button_unchecked").classes(
                    "text-xl " + ("hub-accent" if step.done else "hub-muted")
                )
                with ui.column().classes("gap-1 grow min-w-0"):
                    title = t(f"home.setup.{step.key.value}")
                    if step.optional:
                        title += f" ({t('home.setup.optional')})"
                    ui.label(title).classes("font-medium" + (" line-through hub-muted" if step.done else ""))
                    if not step.done:
                        ui.label(t(f"home.setup.{step.key.value}.detail")).classes("text-sm hub-muted")
                    _step_action(step)


def register_pages() -> None:
    """Register the start page."""

    @ui.page("/")
    async def home_page() -> None:
        today = date.today()
        with frame("home", t("app.title")):
            async with db.session() as session:
                people = {p.id: p for p in await core_service.list_people(session, include_inactive=True)}
                children = await core_service.list_children(session)
                open_episodes = await fever_service.list_episodes(session, open_only=True)
                [schedule] = await rhythm_service.schedule(session, today, 1)
                memories = await time_capsule_service.on_this_day(session, today)
                steps = setup_steps(await load_state(session, get_settings()))

            with ui.column().classes("gap-0"):
                ui.label(_greeting()).classes("text-2xl font-semibold")
                ui.label(t("home.today", weekday=i18n.weekday(today.weekday()), date=i18n.day(today))).classes(
                    "hub-muted"
                )

            if not is_complete(steps) and not app.storage.general.get(DISMISSED_KEY):
                _onboarding(steps)
                if not people:
                    return

            with ui.row().classes("w-full gap-2"):
                for label, path in (
                    (t("home.new_reading"), "/fever"),
                    (t("home.new_memory"), "/time-capsule"),
                    (t("home.new_measurement"), "/growth"),
                    (t("home.week"), "/rhythm"),
                ):
                    ui.button(label, on_click=lambda p=path: ui.navigate.to(p)).props("outline")

            if open_episodes:
                with section(t("home.sick")):
                    for episode in open_episodes:
                        person = people.get(episode.person_id)
                        if person is None:
                            continue
                        with (
                            ui.row()
                            .classes("w-full items-center gap-3 no-wrap cursor-pointer")
                            .on("click", lambda e=episode: ui.navigate.to(f"/fever/episodes/{e.id}"))
                        ):
                            person_dot(person.color)
                            with ui.column().classes("gap-0 grow min-w-0"):
                                ui.label(f"{person.name} · {episode.label}").classes("font-medium truncate")
                                if episode.last_reading:
                                    local = episode.last_reading.measured_at.astimezone(fever_service.local_timezone())
                                    ui.label(
                                        t("home.last_reading", time=f"{i18n.short_day(local)} {local:%H:%M}")
                                    ).classes("text-xs hub-muted")
                            if episode.last_reading:
                                level_label(
                                    f"{i18n.number(episode.last_reading.temperature)} °C",
                                    episode.last_reading.level.value,
                                    "text-xl",
                                )

            with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2"):
                with section(t("home.duties_today")):
                    if not schedule.slots:
                        empty_state(t("home.no_duties"))
                    for time_of_day in TimeOfDay:
                        for slot in [s for s in schedule.slots if s.time_of_day is time_of_day]:
                            person = people.get(slot.person_id) if slot.person_id else None
                            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                                with ui.column().classes("gap-0 grow min-w-0"):
                                    ui.label(slot.duty_name).classes("font-medium truncate")
                                    ui.label(t(f"rhythm.time.{time_of_day.value}")).classes("text-xs hub-muted")
                                if person:
                                    person_dot(person.color)
                                ui.label(person.name if person else t("rhythm.open")).classes(
                                    "text-sm font-medium" if person else "text-sm hub-muted"
                                )

                with section(t("home.children")):
                    if not children:
                        empty_state(
                            t("common.no_children"),
                            t("common.manage_people"),
                            lambda: ui.navigate.to("/people"),
                        )
                    for child in children:
                        with ui.row().classes("w-full items-center gap-3 no-wrap"):
                            with (
                                ui.element("div")
                                .classes("rounded-full flex items-center justify-center text-white font-bold")
                                .style(f"background:{child.color}; width:40px; height:40px; min-width:40px")
                            ):
                                ui.label(child.name[:1].upper())
                            with ui.column().classes("gap-0"):
                                ui.label(child.name).classes("font-medium")
                                ui.label(i18n.format_age(child.age_months)).classes("text-sm hub-muted")

            if memories:
                with section(t("home.on_this_day")):
                    for entry in memories[:3]:
                        years = today.year - entry.date.year
                        with (
                            ui.column()
                            .classes("w-full gap-1 cursor-pointer")
                            .on("click", lambda: ui.navigate.to("/time-capsule"))
                        ):
                            ui.label(f"{t('home.years_ago', n=years)} · {i18n.day(entry.date)}").classes(
                                "text-xs hub-muted"
                            )
                            ui.label(entry.text).classes("text-lg italic whitespace-pre-line")
                            ui.label(", ".join(child.name for child in entry.children)).classes("text-sm hub-muted")
