from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.schemas import PersonWrite
from family_hub.rhythm import service
from family_hub.rhythm.logic import Source, week_start
from family_hub.rhythm.models import RotationPeriod, RuleMode, TimeOfDay
from family_hub.rhythm.schemas import DutyWrite, RuleWrite

TODAY = date.today()
MONDAY = week_start(TODAY)


async def _adults(session: AsyncSession) -> tuple[int, int]:
    a = await core_service.create_person(session, PersonWrite(name="Alex", kind=PersonKind.ADULT))
    b = await core_service.create_person(session, PersonWrite(name="Sam", kind=PersonKind.ADULT))
    return a.id, b.id


async def _duty(session: AsyncSession, weekdays: list[int] | None = None) -> int:
    duty = await service.create_duty(
        session, DutyWrite(name="Bedtime", time_of_day=TimeOfDay.EVENING, weekdays=weekdays or list(range(7)))
    )
    return duty.id


async def test_week_with_fixed_rule_and_swap(session: AsyncSession) -> None:
    alex, sam = await _adults(session)
    duty_id = await _duty(session)
    await service.set_rules(
        session, duty_id, [RuleWrite(weekday=d, mode=RuleMode.FIXED, person_id=alex) for d in range(7)]
    )
    await service.set_swap(session, duty_id, MONDAY + timedelta(days=2), sam)

    week = await service.week(session, TODAY)

    people = [day.slots[0].person_id for day in week.days]
    assert people == [alex, alex, sam, alex, alex, alex, alex]
    assert week.days[2].slots[0].source is Source.SWAP

    await service.remove_swap(session, duty_id, MONDAY + timedelta(days=2))
    week = await service.week(session, TODAY)
    assert week.days[2].slots[0].person_id == alex


async def test_rotation_rule(session: AsyncSession) -> None:
    alex, sam = await _adults(session)
    duty_id = await _duty(session, [0])
    await service.set_rules(
        session,
        duty_id,
        [
            RuleWrite(
                weekday=0,
                mode=RuleMode.ROTATION,
                rotation_person_ids=[alex, sam],
                rotation_period=RotationPeriod.WEEKLY,
                anchor_date=MONDAY,
            )
        ],
    )

    this_week = await service.week(session, MONDAY)
    next_week = await service.week(session, MONDAY + timedelta(weeks=1))

    assert this_week.days[0].slots[0].person_id == alex
    assert next_week.days[0].slots[0].person_id == sam
    assert next_week.days[1].slots == []


async def test_invalid_rules(session: AsyncSession) -> None:
    alex, _ = await _adults(session)
    duty_id = await _duty(session, [0, 1])

    with pytest.raises(ValueError, match="person"):
        await service.set_rules(session, duty_id, [RuleWrite(weekday=0, mode=RuleMode.FIXED)])
    with pytest.raises(ValueError, match="two"):
        await service.set_rules(
            session, duty_id, [RuleWrite(weekday=0, mode=RuleMode.ROTATION, rotation_person_ids=[alex])]
        )
    with pytest.raises(ValueError, match="weekday"):
        await service.set_rules(session, duty_id, [RuleWrite(weekday=5, mode=RuleMode.FIXED, person_id=alex)])


async def test_swap_window(session: AsyncSession) -> None:
    alex, _ = await _adults(session)
    duty_id = await _duty(session)

    with pytest.raises(ValueError, match="current and the next week"):
        await service.set_swap(session, duty_id, MONDAY + timedelta(weeks=3), alex)


async def test_update_drops_rules_of_removed_weekdays(session: AsyncSession) -> None:
    alex, _ = await _adults(session)
    duty_id = await _duty(session, [0, 1])
    await service.set_rules(
        session, duty_id, [RuleWrite(weekday=d, mode=RuleMode.FIXED, person_id=alex) for d in (0, 1)]
    )

    duty = await service.update_duty(
        session, duty_id, DutyWrite(name="Bedtime", time_of_day=TimeOfDay.EVENING, weekdays=[0])
    )

    assert [rule.weekday for rule in duty.rules] == [0]


async def test_move_and_deactivate(session: AsyncSession) -> None:
    first = await _duty(session)
    second = await service.create_duty(session, DutyWrite(name="Kita", time_of_day=TimeOfDay.MORNING, weekdays=[0]))

    await service.move_duty(session, second.id, -1)
    await service.set_active(session, first, active=False)

    assert [d.id for d in await service.list_duties(session, include_inactive=True)] == [second.id, first]
    assert [d.id for d in await service.list_duties(session)] == [second.id]


async def test_duty_stats(session: AsyncSession) -> None:
    alex, sam = await _adults(session)
    duty_id = await _duty(session)
    await service.set_rules(
        session,
        duty_id,
        [RuleWrite(weekday=d, mode=RuleMode.FIXED, person_id=alex if d < 5 else sam) for d in range(6)],
    )

    [stat] = await service.duty_stats(session, MONDAY, MONDAY + timedelta(days=6))

    assert stat.counts == {alex: 5, sam: 1}
    assert stat.open == 1
