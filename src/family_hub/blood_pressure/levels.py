"""Classification of a blood pressure reading for adults.

The default limits are office values: hypertension from 140/90 (German guideline NVL Hypertonie, 2023) and
high-normal from 130/85 (ESC/ESH classification).
"""

from enum import StrEnum

from family_hub.config import Settings, get_settings


class Level(StrEnum):
    """Classification of a single reading."""

    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"


def level_of(systolic: int, diastolic: int, settings: Settings | None = None) -> Level:
    """Classify a reading against the configured limits; the higher of both values decides."""
    settings = settings or get_settings()
    if systolic >= settings.bp_high_systolic or diastolic >= settings.bp_high_diastolic:
        return Level.HIGH
    if systolic >= settings.bp_elevated_systolic or diastolic >= settings.bp_elevated_diastolic:
        return Level.ELEVATED
    return Level.NORMAL
