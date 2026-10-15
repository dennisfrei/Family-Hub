"""Validation errors with translatable messages; `str()` is English (API), the UI shows the user's language."""

MESSAGES: dict[str, tuple[str, str]] = {
    "error.name_required": ("Der Name darf nicht leer sein.", "Name must not be empty"),
    "error.child_profile_required": (
        "Kinder brauchen Geburtsdatum und Geschlecht.",
        "Children need a birth date and sex",
    ),
    "error.token_days": (
        "Die Gültigkeit muss zwischen 1 und {max} Tagen liegen.",
        "Validity must be between 1 and {max} days",
    ),
    "error.label_required": ("Die Bezeichnung darf nicht leer sein.", "Label must not be empty"),
    "error.temperature_range": (
        "Die Temperatur muss zwischen {low} und {high} °C liegen.",
        "Temperature must be between {low} and {high} °C",
    ),
    "error.value_range": (
        "Der Wert muss zwischen {low} und {high} {unit} liegen.",
        "{type} must be between {low} and {high} {unit}",
    ),
    "error.before_birth": ("Das Datum liegt vor der Geburt.", "Date is before the birth date"),
    "error.future_date": ("Das Datum liegt in der Zukunft.", "Date is in the future"),
    "error.text_required": ("Der Text darf nicht leer sein.", "Text must not be empty"),
    "error.child_required": ("Mindestens ein Kind auswählen.", "Choose at least one child"),
    "error.weekday_required": ("Mindestens einen Wochentag auswählen.", "Choose at least one weekday"),
    "error.rule_weekday": (
        "Der Dienst findet an diesem Wochentag nicht statt.",
        "Duty does not occur on weekday {day}",
    ),
    "error.fixed_needs_person": ("Eine feste Regel braucht eine Person.", "A fixed rule needs a person"),
    "error.rotation_needs_two": (
        "Eine Rotation braucht mindestens zwei Personen.",
        "A rotation needs at least two people",
    ),
    "error.one_rule_per_weekday": ("Nur eine Regel pro Wochentag.", "Only one rule per weekday"),
    "error.swap_window": (
        "Tauschen geht nur für diese und nächste Woche.",
        "Swaps are only possible for the current and the next week",
    ),
    "error.duty_not_on_day": ("Der Dienst findet an diesem Tag nicht statt.", "The duty does not occur on that day"),
}


class InvalidInputError(ValueError):
    """Raised by services for invalid user input."""

    def __init__(self, key: str, **params: object) -> None:
        """Create the error from a message key and its placeholders."""
        self.key = key
        self.params = params
        super().__init__(MESSAGES[key][1].format(**params))
