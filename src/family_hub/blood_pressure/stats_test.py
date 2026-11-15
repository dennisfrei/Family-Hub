from datetime import UTC, datetime, timedelta

from family_hub.blood_pressure.levels import Level
from family_hub.blood_pressure.schemas import ReadingRead
from family_hub.blood_pressure.stats import recent_average
from family_hub.config import Settings

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
SETTINGS = Settings(_env_file=None)


def _reading(days_ago: float, systolic: int, diastolic: int = 80, pulse: int | None = 60) -> ReadingRead:
    return ReadingRead(
        id=1,
        person_id=1,
        systolic=systolic,
        diastolic=diastolic,
        pulse=pulse,
        measured_at=NOW - timedelta(days=days_ago),
        level=Level.NORMAL,
    )


def test_last_seven_days_when_they_hold_enough() -> None:
    readings = [_reading(day / 2, 140, 90) for day in range(8)] + [_reading(20, 100, 60)]

    average = recent_average(readings, NOW, SETTINGS)

    assert average is not None
    assert (average.systolic, average.diastolic, average.count, average.by_days) == (140, 90, 8, True)
    assert average.level is Level.HIGH


def test_latest_seven_readings_otherwise() -> None:
    readings = [_reading(1, 130, pulse=None), *(_reading(10 + day, 120, pulse=70) for day in range(9))]

    average = recent_average(readings, NOW, SETTINGS)

    assert average is not None
    assert (average.systolic, average.pulse, average.count, average.by_days) == (121, 70, 7, False)


def test_needs_two_readings() -> None:
    assert recent_average([_reading(1, 120)], NOW, SETTINGS) is None
