from datetime import date, timedelta

import pytest

from family_hub.rhythm.logic import (
    RuleSpec,
    Source,
    mask_to_weekdays,
    resolve,
    rotation_index,
    week_start,
    weekdays_to_mask,
)
from family_hub.rhythm.models import RotationPeriod, RuleMode

MONDAY = date(2026, 10, 12)


def test_weekday_mask_roundtrip() -> None:
    assert mask_to_weekdays(weekdays_to_mask([0, 4, 6])) == [0, 4, 6]
    with pytest.raises(ValueError, match="weekday"):
        weekdays_to_mask([7])


def test_week_start() -> None:
    assert week_start(date(2026, 10, 18)) == MONDAY


def test_swap_wins() -> None:
    rule = RuleSpec(mode=RuleMode.FIXED, person_id=1)

    assert resolve(rule, 2, MONDAY, {1, 2}).person_id == 2
    assert resolve(rule, 2, MONDAY, {1, 2}).source is Source.SWAP


def test_fixed_and_open() -> None:
    assert resolve(RuleSpec(mode=RuleMode.FIXED, person_id=1), None, MONDAY, {1}).person_id == 1
    assert resolve(None, None, MONDAY, {1}).source is Source.OPEN


def test_fixed_inactive_person_is_open_with_warning() -> None:
    assignment = resolve(RuleSpec(mode=RuleMode.FIXED, person_id=1), None, MONDAY, {2})

    assert assignment.source is Source.OPEN
    assert assignment.warning


def test_weekly_rotation_is_stable_across_weeks() -> None:
    rule = RuleSpec(mode=RuleMode.ROTATION, rotation=(1, 2), period=RotationPeriod.WEEKLY, anchor=MONDAY)
    people = [resolve(rule, None, MONDAY + timedelta(weeks=w, days=2), {1, 2}).person_id for w in range(4)]

    assert people == [1, 2, 1, 2]


def test_daily_rotation_and_dates_before_anchor() -> None:
    assert rotation_index(MONDAY + timedelta(days=4), MONDAY, RotationPeriod.DAILY, 3) == 1
    assert rotation_index(MONDAY - timedelta(days=1), MONDAY, RotationPeriod.DAILY, 3) == 2


def test_rotation_skips_inactive_people() -> None:
    rule = RuleSpec(mode=RuleMode.ROTATION, rotation=(1, 2, 3), period=RotationPeriod.DAILY, anchor=MONDAY)

    assignment = resolve(rule, None, MONDAY + timedelta(days=1), {1, 3})

    assert assignment.person_id == 3
    assert assignment.warning
