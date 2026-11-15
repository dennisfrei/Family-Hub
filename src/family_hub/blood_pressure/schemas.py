"""DTOs for the blood pressure API and service layer."""

from datetime import date, datetime, time

from pydantic import BaseModel

from family_hub.blood_pressure.levels import Level

SYSTOLIC_RANGE = (60, 260)
DIASTOLIC_RANGE = (30, 160)
PULSE_RANGE = (30, 220)


class Measurement(BaseModel):
    """The values shown on a blood pressure monitor (mmHg, beats per minute)."""

    systolic: int
    diastolic: int
    pulse: int | None = None


class ListEntry(BaseModel):
    """One line of a photographed list of readings; None where nothing could be read."""

    day: date | None = None
    at: time | None = None
    systolic: int | None = None
    diastolic: int | None = None
    pulse: int | None = None


class ReadingWrite(Measurement):
    """A new reading; `measured_at` defaults to now."""

    person_id: int
    measured_at: datetime | None = None
    note: str | None = None


class ReadingRead(Measurement):
    """A reading with its classification."""

    id: int
    person_id: int
    measured_at: datetime
    level: Level
    note: str | None = None
