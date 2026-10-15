"""UI translations (German default, English) and locale-aware formatting.

Each module registers its texts with `register`; the language is stored per browser.
"""

from datetime import date, datetime
from enum import StrEnum

from nicegui import app

from family_hub.errors import MESSAGES, InvalidInputError


class Language(StrEnum):
    """Supported UI languages."""

    DE = "de"
    EN = "en"


DEFAULT_LANGUAGE = Language.DE
STORAGE_KEY = "language"

_TEXTS: dict[str, tuple[str, str]] = {}


def register(texts: dict[str, tuple[str, str]]) -> None:
    """Add texts as `{key: (german, english)}`."""
    _TEXTS.update(texts)


def language() -> Language:
    """Return the current browser's language, or the default outside a page."""
    try:
        return Language(app.storage.user.get(STORAGE_KEY, DEFAULT_LANGUAGE.value))
    except (RuntimeError, ValueError, AssertionError):
        return DEFAULT_LANGUAGE


def set_language(value: Language) -> None:
    """Remember the language for the current browser."""
    app.storage.user[STORAGE_KEY] = value.value


def t(key: str, **values: object) -> str:
    """Translate a key; unknown keys are returned as they are."""
    texts = _TEXTS.get(key)
    if texts is None:
        return key
    text = texts[0] if language() is Language.DE else texts[1]
    return text.format(**values) if values else text


def error_text(exc: Exception) -> str:
    """Message of a service error in the current language."""
    if isinstance(exc, InvalidInputError):
        return t(exc.key, **exc.params)
    return str(exc)


def number(value: float, digits: int = 1) -> str:
    """Format a number with the language's decimal separator."""
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if language() is Language.DE else text


def signed(value: float, digits: int = 1) -> str:
    """Format a number with sign."""
    text = f"{value:+.{digits}f}"
    return text.replace(".", ",") if language() is Language.DE else text


def day(value: date | datetime) -> str:
    """Format a date."""
    return f"{value:%d.%m.%Y}" if language() is Language.DE else f"{value:%Y-%m-%d}"


def short_day(value: date | datetime) -> str:
    """Format a date without year."""
    return f"{value:%d.%m.}" if language() is Language.DE else f"{value:%m-%d}"


def short_day_format() -> str:
    """Date pattern of `short_day` in strftime syntax, e.g. for chart axes."""
    return "%d.%m." if language() is Language.DE else "%m-%d"


def day_range(start: date, end: date) -> str:
    """Format a date range; the German form leaves out the first year."""
    if language() is Language.DE:
        return f"{start:%d.%m.} – {end:%d.%m.%Y}"
    return f"{start:%Y-%m-%d} – {end:%Y-%m-%d}"


def weekday(index: int) -> str:
    """Full weekday name, Monday = 0."""
    return t(f"weekday.{index}")


def weekday_short(index: int) -> str:
    """Short weekday name, Monday = 0."""
    return t(f"weekday_short.{index}")


def month_year(value: date) -> str:
    """Month name and year, e.g. `März 2026`."""
    return f"{t(f'month.{value.month}')} {value.year}"


def format_age(months: int) -> str:
    """Age from completed months, e.g. `3 J. 4 Mon.` / `3 y 4 m`."""
    years, rest = divmod(max(months, 0), 12)
    if years == 0:
        return t("age.months", m=rest)
    if rest == 0:
        return t("age.years", y=years)
    return t("age.years_months", y=years, m=rest)


register(MESSAGES)
register(
    {
        "age.months": ("{m} Mon.", "{m} m"),
        "age.years": ("{y} J.", "{y} y"),
        "age.years_months": ("{y} J. {m} Mon.", "{y} y {m} m"),
        **{
            f"weekday.{i}": names
            for i, names in enumerate(
                [
                    ("Montag", "Monday"),
                    ("Dienstag", "Tuesday"),
                    ("Mittwoch", "Wednesday"),
                    ("Donnerstag", "Thursday"),
                    ("Freitag", "Friday"),
                    ("Samstag", "Saturday"),
                    ("Sonntag", "Sunday"),
                ]
            )
        },
        **{
            f"weekday_short.{i}": names
            for i, names in enumerate(
                [
                    ("Mo", "Mon"),
                    ("Di", "Tue"),
                    ("Mi", "Wed"),
                    ("Do", "Thu"),
                    ("Fr", "Fri"),
                    ("Sa", "Sat"),
                    ("So", "Sun"),
                ]
            )
        },
        **{
            f"month.{i}": names
            for i, names in enumerate(
                [
                    ("Januar", "January"),
                    ("Februar", "February"),
                    ("März", "March"),
                    ("April", "April"),
                    ("Mai", "May"),
                    ("Juni", "June"),
                    ("Juli", "July"),
                    ("August", "August"),
                    ("September", "September"),
                    ("Oktober", "October"),
                    ("November", "November"),
                    ("Dezember", "December"),
                ],
                start=1,
            )
        },
        "common.save": ("Speichern", "Save"),
        "common.cancel": ("Abbrechen", "Cancel"),
        "common.delete": ("Löschen", "Delete"),
        "common.edit": ("Bearbeiten", "Edit"),
        "common.add": ("Hinzufügen", "Add"),
        "common.create": ("Anlegen", "Create"),
        "common.back": ("Zurück", "Back"),
        "common.date": ("Datum", "Date"),
        "common.time": ("Uhrzeit", "Time"),
        "common.name": ("Name", "Name"),
        "common.note_optional": ("Notiz (optional)", "Note (optional)"),
        "common.description_optional": ("Beschreibung (optional)", "Description (optional)"),
        "common.color": ("Farbe", "Color"),
        "common.all": ("Alle", "All"),
        "common.none": ("Keine", "None"),
        "common.search": ("Suchen", "Search"),
        "common.saved": ("Gespeichert", "Saved"),
        "common.deleted": ("Gelöscht", "Deleted"),
        "common.invalid_date": ("Ungültiges Datum oder Uhrzeit", "Invalid date or time"),
        "common.no_children": ("Noch keine Kinder angelegt.", "No children yet."),
        "common.manage_people": ("Personen verwalten", "Manage people"),
        "common.today": ("Heute", "Today"),
        "common.download": ("Herunterladen", "Download"),
        "layout.dark_mode": ("Dunkles Design", "Dark mode"),
        "layout.language": ("Sprache", "Language"),
        "layout.refresh": ("Neu laden", "Reload"),
        "layout.logout": ("Abmelden", "Sign out"),
    }
)
