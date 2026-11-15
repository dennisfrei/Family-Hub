"""Average of the recent readings of a person."""

from datetime import datetime, timedelta

from pydantic import BaseModel

from family_hub.blood_pressure.levels import Level, level_of
from family_hub.blood_pressure.schemas import ReadingRead
from family_hub.config import Settings

WINDOW_DAYS = 7
WINDOW_COUNT = 7
MIN_READINGS = 2


class Average(BaseModel):
    """Mean values over the recent readings."""

    systolic: int
    diastolic: int
    pulse: int | None
    count: int
    by_days: bool
    level: Level


def recent_average(readings: list[ReadingRead], now: datetime, settings: Settings | None = None) -> Average | None:
    """Average the last seven days, or the latest seven readings if those days hold fewer.

    Args:
        readings: Readings of one person, newest first.
        now: Current time with timezone.
        settings: App settings for the level limits; defaults to the process settings.

    Returns:
        The average, or None with fewer than two readings.
    """
    in_days = [reading for reading in readings if reading.measured_at >= now - timedelta(days=WINDOW_DAYS)]
    by_days = len(in_days) >= WINDOW_COUNT
    chosen = in_days if by_days else readings[:WINDOW_COUNT]
    if len(chosen) < MIN_READINGS:
        return None
    systolic = round(sum(reading.systolic for reading in chosen) / len(chosen))
    diastolic = round(sum(reading.diastolic for reading in chosen) / len(chosen))
    pulses = [reading.pulse for reading in chosen if reading.pulse is not None]
    return Average(
        systolic=systolic,
        diastolic=diastolic,
        pulse=round(sum(pulses) / len(pulses)) if pulses else None,
        count=len(chosen),
        by_days=by_days,
        level=level_of(systolic, diastolic, settings),
    )
