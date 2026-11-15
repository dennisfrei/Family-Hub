"""Date and time fields shown in the UI language, with a picker instead of the browser's native input."""

from datetime import date, time

from nicegui import ui

from family_hub.ui import i18n
from family_hub.ui.i18n import t


def _quasar_locale() -> dict[str, object]:
    days = [i18n.weekday((index - 1) % 7) for index in range(7)]
    return {
        "days": days,
        "daysShort": [i18n.weekday_short((index - 1) % 7) for index in range(7)],
        "months": [t(f"month.{month}") for month in range(1, 13)],
        "monthsShort": [t(f"month.{month}")[:3] for month in range(1, 13)],
        "firstDayOfWeek": 1,
    }


def _popup() -> ui.element:
    """A popup that is a menu on wide screens and a centered dialog on phones, so the picker is never clipped."""
    return ui.element("q-popup-proxy").props("breakpoint=600")


class DateField:
    """A read-only input showing the formatted date; tapping opens a calendar."""

    def __init__(self, label: str, value: date | None = None, *, clearable: bool = False) -> None:
        """Create the field inside the current container."""
        self._value = value
        self.input = ui.input(label, value=self._text()).props("outlined dense readonly").classes("w-full")
        if clearable:
            self.input.props("clearable").on("clear", lambda: self._set(None))
        with self.input, _popup() as self.popup:
            self.picker = ui.date(value=value.isoformat() if value else None, on_change=self._picked).props(
                "minimal first-day-of-week=1"
            )
            self.picker.props["locale"] = _quasar_locale()

    def _text(self) -> str:
        return i18n.day(self._value) if self._value else ""

    def _picked(self, event: object) -> None:
        picked = getattr(event, "value", None)
        self._set(date.fromisoformat(picked) if picked else None)
        self.popup.run_method("hide")

    def _set(self, value: date | None) -> None:
        self._value = value
        self.input.value = self._text()

    @property
    def value(self) -> date | None:
        """The selected date."""
        return self._value

    @value.setter
    def value(self, value: date | None) -> None:
        self._set(value)
        self.picker.value = value.isoformat() if value else None

    def classes(self, add: str) -> "DateField":
        """Add classes to the input."""
        self.input.classes(add)
        return self


class TimeField:
    """A read-only input showing HH:MM; tapping opens a 24-hour clock."""

    def __init__(self, label: str, value: time) -> None:
        """Create the field inside the current container."""
        self._value = value
        self.input = ui.input(label, value=f"{value:%H:%M}").props("outlined dense readonly").classes("w-full")
        with self.input, _popup() as popup:
            self.picker = ui.time(value=f"{value:%H:%M}", on_change=self._picked).props("format24h minimal")
            with self.picker, ui.row().classes("w-full justify-end"):
                ui.button(t("common.ok"), on_click=lambda: popup.run_method("hide")).props("flat dense")

    def _picked(self, event: object) -> None:
        picked = getattr(event, "value", None)
        if picked:
            self._value = time.fromisoformat(picked)
            self.input.value = f"{self._value:%H:%M}"

    @property
    def value(self) -> time:
        """The selected time."""
        return self._value

    def classes(self, add: str) -> "TimeField":
        """Add classes to the input."""
        self.input.classes(add)
        return self
