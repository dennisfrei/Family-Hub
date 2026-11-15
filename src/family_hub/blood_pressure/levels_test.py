import pytest

from family_hub.blood_pressure.levels import Level, level_of
from family_hub.config import Settings


@pytest.mark.parametrize(
    ("systolic", "diastolic", "expected"),
    [
        (118, 76, Level.NORMAL),
        (129, 84, Level.NORMAL),
        (130, 80, Level.ELEVATED),
        (120, 85, Level.ELEVATED),
        (140, 80, Level.HIGH),
        (125, 90, Level.HIGH),
    ],
)
def test_level(systolic: int, diastolic: int, expected: Level) -> None:
    assert level_of(systolic, diastolic, Settings(_env_file=None)) is expected


def test_limits_from_settings() -> None:
    home = Settings(bp_high_systolic=135, bp_high_diastolic=85, bp_elevated_systolic=120, bp_elevated_diastolic=70)

    assert level_of(136, 80, home) is Level.HIGH
    assert level_of(118, 72, home) is Level.ELEVATED
    assert level_of(118, 68, home) is Level.NORMAL
