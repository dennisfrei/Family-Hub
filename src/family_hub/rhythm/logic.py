"""Pure assignment logic: swap → rule (fixed or rotation) → open."""

from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from family_hub.rhythm.models import RotationPeriod, RuleMode

DAYS_PER_WEEK = 7


class Source(StrEnum):
    """Where an assignment comes from."""

    SWAP = "swap"
    RULE = "rule"
    OPEN = "open"


class RuleSpec(BaseModel):
    """A weekday rule reduced to what the resolution needs."""

    model_config = ConfigDict(frozen=True)

    mode: RuleMode
    person_id: int | None = None
    rotation: tuple[int, ...] = ()
    period: RotationPeriod | None = None
    anchor: date | None = None


class Assignment(BaseModel):
    """Resolved assignee; `warning` when the rule points to inactive people only."""

    model_config = ConfigDict(frozen=True)

    person_id: int | None
    source: Source
    warning: bool = False


def weekdays_to_mask(weekdays: list[int]) -> int:
    """Bitmask with Monday = bit 0."""
    mask = 0
    for day in weekdays:
        if not 0 <= day < DAYS_PER_WEEK:
            raise ValueError(f"Invalid weekday {day}")
        mask |= 1 << day
    return mask


def mask_to_weekdays(mask: int) -> list[int]:
    """Weekdays (Monday = 0) contained in a bitmask."""
    return [day for day in range(DAYS_PER_WEEK) if mask & (1 << day)]


def week_start(day: date) -> date:
    """Monday of the day's week."""
    return day - timedelta(days=day.weekday())


def rotation_index(day: date, anchor: date, period: RotationPeriod, length: int) -> int:
    """Position in a rotation of `length` people on `day`, stable across weeks."""
    if period is RotationPeriod.WEEKLY:
        steps = (week_start(day) - week_start(anchor)).days // DAYS_PER_WEEK
    else:
        steps = (day - anchor).days
    return steps % length


def resolve(rule: RuleSpec | None, swap_person_id: int | None, day: date, active_ids: set[int]) -> Assignment:
    """Assignee of a duty on a day; inactive people are skipped for rules, not for swaps."""
    if swap_person_id is not None:
        return Assignment(person_id=swap_person_id, source=Source.SWAP)
    if rule is None:
        return Assignment(person_id=None, source=Source.OPEN)
    if rule.mode is RuleMode.FIXED:
        if rule.person_id is None:
            return Assignment(person_id=None, source=Source.OPEN)
        if rule.person_id not in active_ids:
            return Assignment(person_id=None, source=Source.OPEN, warning=True)
        return Assignment(person_id=rule.person_id, source=Source.RULE)
    members = [person_id for person_id in rule.rotation if person_id in active_ids]
    if not members:
        return Assignment(person_id=None, source=Source.OPEN, warning=bool(rule.rotation))
    index = rotation_index(day, rule.anchor or day, rule.period or RotationPeriod.WEEKLY, len(members))
    return Assignment(person_id=members[index], source=Source.RULE, warning=len(members) < len(rule.rotation))
