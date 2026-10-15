from datetime import date

import pytest

from family_hub.ui import i18n


@pytest.mark.parametrize(("months", "expected"), [(5, "5 Mon."), (24, "2 J."), (40, "3 J. 4 Mon.")])
def test_format_age_default_german(months: int, expected: str) -> None:
    assert i18n.format_age(months) == expected


def test_english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "language", lambda: i18n.Language.EN)

    assert i18n.format_age(40) == "3 y 4 m"
    assert i18n.number(37.55, 1) == "37.5" or i18n.number(37.55, 1) == "37.6"
    assert i18n.day(date(2026, 3, 1)) == "2026-03-01"
    assert i18n.t("weekday.0") == "Monday"


def test_german_formatting() -> None:
    assert i18n.number(38.25, 2) == "38,25"
    assert i18n.day(date(2026, 3, 1)) == "01.03.2026"
    assert i18n.month_year(date(2026, 3, 1)) == "März 2026"


def test_unknown_key_and_placeholders() -> None:
    assert i18n.t("does.not.exist") == "does.not.exist"
    assert i18n.t("age.months", m=3) == "3 Mon."


@pytest.mark.parametrize(
    ("lang", "expected"),
    [(i18n.Language.DE, "12.10. – 18.10.2026"), (i18n.Language.EN, "2026-10-12 – 2026-10-18")],
)
def test_day_range(monkeypatch: pytest.MonkeyPatch, lang: i18n.Language, expected: str) -> None:
    monkeypatch.setattr(i18n, "language", lambda: lang)

    assert i18n.day_range(date(2026, 10, 12), date(2026, 10, 18)) == expected
