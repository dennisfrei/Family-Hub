from datetime import date

import pytest

from family_hub.config import Settings
from family_hub.fever.thresholds import AgeGroup, Level, age_group, thresholds_for


@pytest.mark.parametrize(
    ("birth_date", "expected"),
    [
        (date(2026, 8, 1), AgeGroup.INFANT),
        (date(2026, 7, 14), AgeGroup.CHILD),
        (date(2014, 10, 15), AgeGroup.CHILD),
        (date(2014, 10, 14), AgeGroup.ADULT),
        (None, AgeGroup.ADULT),
    ],
)
def test_age_group(birth_date: date | None, expected: AgeGroup) -> None:
    assert age_group(birth_date, date(2026, 10, 14)) is expected


def test_thresholds_from_settings() -> None:
    settings = Settings(_env_file=None, fever_threshold_child=38.3, elevated_threshold_child=37.4)

    thresholds = thresholds_for(AgeGroup.CHILD, settings)

    assert (thresholds.fever, thresholds.elevated) == (38.3, 37.4)


@pytest.mark.parametrize(("temperature", "level"), [(37.4, Level.NORMAL), (37.5, Level.ELEVATED), (38.5, Level.FEVER)])
def test_level(temperature: float, level: Level) -> None:
    assert thresholds_for(AgeGroup.CHILD, Settings(_env_file=None)).level(temperature) is level
