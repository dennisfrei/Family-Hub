"""Age-based fever thresholds, configurable via settings."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from family_hub.config import Settings, get_settings
from family_hub.core.service import age_in_months

INFANT_MAX_MONTHS = 3
CHILD_MAX_MONTHS = 12 * 12


class AgeGroup(StrEnum):
    """Age groups with their own thresholds (infant < 3 months, child < 12 years)."""

    INFANT = "infant"
    CHILD = "child"
    ADULT = "adult"


class Level(StrEnum):
    """Classification of a single temperature."""

    NORMAL = "normal"
    ELEVATED = "elevated"
    FEVER = "fever"


class Thresholds(BaseModel):
    """Thresholds in °C for one age group."""

    model_config = ConfigDict(frozen=True)

    age_group: AgeGroup
    fever: float
    elevated: float

    def level(self, temperature: float) -> Level:
        """Classify a temperature."""
        if temperature >= self.fever:
            return Level.FEVER
        if temperature >= self.elevated:
            return Level.ELEVATED
        return Level.NORMAL


def age_group(birth_date: date | None, on: date) -> AgeGroup:
    """Return the age group on a date; people without birth date count as adults."""
    if birth_date is None:
        return AgeGroup.ADULT
    months = age_in_months(birth_date, on)
    if months < INFANT_MAX_MONTHS:
        return AgeGroup.INFANT
    if months < CHILD_MAX_MONTHS:
        return AgeGroup.CHILD
    return AgeGroup.ADULT


def thresholds_for(group: AgeGroup, settings: Settings | None = None) -> Thresholds:
    """Return the configured thresholds of an age group."""
    settings = settings or get_settings()
    return Thresholds(
        age_group=group,
        fever=getattr(settings, f"fever_threshold_{group.value}"),
        elevated=getattr(settings, f"elevated_threshold_{group.value}"),
    )
