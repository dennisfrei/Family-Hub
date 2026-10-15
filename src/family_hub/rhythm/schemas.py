"""DTOs for the rhythm API and service layer."""

import datetime as dt

from pydantic import BaseModel

from family_hub.rhythm.logic import Source
from family_hub.rhythm.models import DEFAULT_COLOR, DEFAULT_ICON, RotationPeriod, RuleMode, TimeOfDay


class DutyWrite(BaseModel):
    """Data to create or replace a duty; weekdays with Monday = 0."""

    name: str
    time_of_day: TimeOfDay
    weekdays: list[int]
    icon: str = DEFAULT_ICON
    color: str = DEFAULT_COLOR
    for_person_id: int | None = None


class RuleWrite(BaseModel):
    """The rule for one weekday."""

    weekday: int
    mode: RuleMode
    person_id: int | None = None
    rotation_person_ids: list[int] = []
    rotation_period: RotationPeriod | None = None
    anchor_date: dt.date | None = None


class RuleRead(RuleWrite):
    """A stored rule."""


class DutyRead(BaseModel):
    """A duty with its rules."""

    id: int
    name: str
    icon: str
    color: str
    time_of_day: TimeOfDay
    weekdays: list[int]
    is_preset: bool
    active: bool
    sort_order: int
    rules: list[RuleRead]
    for_person_id: int | None = None


class SlotRead(BaseModel):
    """A duty on one date with its resolved assignee."""

    duty_id: int
    duty_name: str
    icon: str
    color: str
    time_of_day: TimeOfDay
    date: dt.date
    source: Source
    person_id: int | None = None
    warning: bool = False
    for_person_id: int | None = None


class DayRead(BaseModel):
    """All slots of one day, in duty order."""

    date: dt.date
    slots: list[SlotRead]


class WeekRead(BaseModel):
    """A resolved week, Monday to Sunday."""

    start: dt.date
    days: list[DayRead]


class SwapWrite(BaseModel):
    """A one-off assignee."""

    duty_id: int
    date: dt.date
    person_id: int


class DutyStat(BaseModel):
    """How often each person did a duty in a period; `open` counts slots without anyone."""

    duty_id: int
    duty_name: str
    color: str
    counts: dict[int, int]
    open: int = 0
