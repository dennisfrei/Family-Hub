"""Business logic for duties, rules, swaps and the weekly schedule; the only place touching rhythm tables."""

import logging
from datetime import date, timedelta

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.errors import InvalidInputError
from family_hub.rhythm.logic import DAYS_PER_WEEK, RuleSpec, mask_to_weekdays, resolve, week_start, weekdays_to_mask
from family_hub.rhythm.models import Duty, RotationMember, RotationPeriod, Rule, RuleMode, Swap
from family_hub.rhythm.schemas import DayRead, DutyRead, DutyStat, DutyWrite, RuleRead, RuleWrite, SlotRead, WeekRead

logger = logging.getLogger(__name__)

SWAP_WEEKS = 2


class NotFoundError(LookupError):
    """Raised when a duty does not exist."""


def _rule_read(rule: Rule) -> RuleRead:
    return RuleRead(
        weekday=rule.weekday,
        mode=rule.mode,
        person_id=rule.person_id,
        rotation_person_ids=[member.person_id for member in rule.rotation],
        rotation_period=rule.rotation_period,
        anchor_date=rule.anchor_date,
    )


def _duty_read(duty: Duty) -> DutyRead:
    return DutyRead(
        id=duty.id,
        name=duty.name,
        icon=duty.icon,
        color=duty.color,
        time_of_day=duty.time_of_day,
        weekdays=mask_to_weekdays(duty.weekdays),
        is_preset=duty.is_preset,
        active=duty.active,
        sort_order=duty.sort_order,
        rules=[_rule_read(rule) for rule in duty.rules],
        for_person_id=duty.for_person_id,
    )


async def _load(session: AsyncSession, duty_id: int) -> Duty:
    duty = await session.get(Duty, duty_id)
    if duty is None:
        raise NotFoundError(f"Duty {duty_id} not found")
    return duty


def _validate(data: DutyWrite) -> None:
    if not data.name.strip():
        raise InvalidInputError("error.name_required")
    if not data.weekdays:
        raise InvalidInputError("error.weekday_required")
    weekdays_to_mask(data.weekdays)


async def list_duties(session: AsyncSession, *, include_inactive: bool = False) -> list[DutyRead]:
    """List duties in display order."""
    query = select(Duty).order_by(Duty.sort_order, Duty.id)
    if not include_inactive:
        query = query.where(Duty.active.is_(True))
    return [_duty_read(duty) for duty in await session.scalars(query)]


async def get_duty(session: AsyncSession, duty_id: int) -> DutyRead:
    """Return one duty.

    Raises:
        NotFoundError: If the duty does not exist.
    """
    return _duty_read(await _load(session, duty_id))


async def create_duty(session: AsyncSession, data: DutyWrite) -> DutyRead:
    """Create a custom duty at the end of the list.

    Raises:
        ValueError: If name or weekdays are invalid.
    """
    _validate(data)
    last = await session.scalar(select(Duty.sort_order).order_by(Duty.sort_order.desc()).limit(1))
    duty = Duty(
        name=data.name.strip(),
        icon=data.icon,
        color=data.color,
        time_of_day=data.time_of_day,
        weekdays=weekdays_to_mask(data.weekdays),
        for_person_id=data.for_person_id,
        is_preset=False,
        active=True,
        sort_order=(last or 0) + 1,
        rules=[],
    )
    session.add(duty)
    await session.commit()
    logger.info(f"Created duty {duty.id}")
    return _duty_read(duty)


async def update_duty(session: AsyncSession, duty_id: int, data: DutyWrite) -> DutyRead:
    """Replace a duty's fields; rules for removed weekdays are dropped.

    Raises:
        NotFoundError: If the duty does not exist.
        ValueError: If name or weekdays are invalid.
    """
    _validate(data)
    duty = await _load(session, duty_id)
    duty.name = data.name.strip()
    duty.icon = data.icon
    duty.color = data.color
    duty.time_of_day = data.time_of_day
    duty.weekdays = weekdays_to_mask(data.weekdays)
    duty.for_person_id = data.for_person_id
    duty.rules = [rule for rule in duty.rules if rule.weekday in data.weekdays]
    await session.commit()
    return _duty_read(duty)


async def set_active(session: AsyncSession, duty_id: int, *, active: bool) -> DutyRead:
    """Activate or deactivate a duty.

    Raises:
        NotFoundError: If the duty does not exist.
    """
    duty = await _load(session, duty_id)
    duty.active = active
    await session.commit()
    return _duty_read(duty)


async def delete_duty(session: AsyncSession, duty_id: int) -> None:
    """Delete a duty with its rules and swaps (presets too).

    Raises:
        NotFoundError: If the duty does not exist.
    """
    await session.delete(await _load(session, duty_id))
    await session.commit()
    logger.info(f"Deleted duty {duty_id}")


async def move_duty(session: AsyncSession, duty_id: int, offset: int) -> None:
    """Move a duty up (-1) or down (+1) in the display order.

    Raises:
        NotFoundError: If the duty does not exist.
    """
    duties = list(await session.scalars(select(Duty).order_by(Duty.sort_order, Duty.id)))
    index = next((i for i, duty in enumerate(duties) if duty.id == duty_id), None)
    if index is None:
        raise NotFoundError(f"Duty {duty_id} not found")
    target = min(max(index + offset, 0), len(duties) - 1)
    duties.insert(target, duties.pop(index))
    for position, duty in enumerate(duties):
        duty.sort_order = position
    await session.commit()


def _validate_rule(rule: RuleWrite, weekdays: list[int]) -> None:
    if rule.weekday not in weekdays:
        raise InvalidInputError("error.rule_weekday", day=rule.weekday)
    if rule.mode is RuleMode.FIXED and rule.person_id is None:
        raise InvalidInputError("error.fixed_needs_person")
    if rule.mode is RuleMode.ROTATION and len(rule.rotation_person_ids) < 2:
        raise InvalidInputError("error.rotation_needs_two")


async def set_rules(session: AsyncSession, duty_id: int, rules: list[RuleWrite]) -> DutyRead:
    """Replace all rules of a duty; weekdays without rule stay open.

    Raises:
        NotFoundError: If the duty does not exist.
        ValueError: If a rule is incomplete or a person does not exist.
    """
    duty = await _load(session, duty_id)
    weekdays = mask_to_weekdays(duty.weekdays)
    if len({rule.weekday for rule in rules}) != len(rules):
        raise InvalidInputError("error.one_rule_per_weekday")
    for rule in rules:
        _validate_rule(rule, weekdays)
        person_ids = set(rule.rotation_person_ids)
        if rule.person_id is not None:
            person_ids.add(rule.person_id)
        for person_id in person_ids:
            await core_service.get_person(session, person_id)
    duty.rules = []
    await session.flush()
    duty.rules = [
        Rule(
            weekday=rule.weekday,
            mode=rule.mode,
            person_id=rule.person_id if rule.mode is RuleMode.FIXED else None,
            rotation_period=(rule.rotation_period or RotationPeriod.WEEKLY) if rule.mode is RuleMode.ROTATION else None,
            anchor_date=(rule.anchor_date or date.today()) if rule.mode is RuleMode.ROTATION else None,
            rotation=[
                RotationMember(position=position, person_id=person_id)
                for position, person_id in enumerate(rule.rotation_person_ids if rule.mode is RuleMode.ROTATION else [])
            ],
        )
        for rule in rules
    ]
    await session.commit()
    logger.info(f"Set {len(rules)} rules for duty {duty_id}")
    return _duty_read(await _load(session, duty_id))


def swap_window(today: date) -> tuple[date, date]:
    """First and last date swaps are allowed for: the current and the next week."""
    start = week_start(today)
    return start, start + timedelta(days=SWAP_WEEKS * DAYS_PER_WEEK - 1)


async def set_swap(
    session: AsyncSession, duty_id: int, day: date, person_id: int, *, today: date | None = None
) -> None:
    """Assign a person for one date, replacing an existing swap.

    Raises:
        NotFoundError: If the duty does not exist.
        ValueError: If the date is outside the current and next week or the duty does not occur then.
    """
    first, last = swap_window(today or date.today())
    if not first <= day <= last:
        raise InvalidInputError("error.swap_window")
    duty = await _load(session, duty_id)
    if day.weekday() not in mask_to_weekdays(duty.weekdays):
        raise InvalidInputError("error.duty_not_on_day")
    await core_service.get_person(session, person_id)
    swap = await session.scalar(select(Swap).where(Swap.duty_id == duty_id, Swap.day == day))
    if swap is None:
        session.add(Swap(duty_id=duty_id, day=day, person_id=person_id))
    else:
        swap.person_id = person_id
    await session.commit()
    logger.info(f"Swap for duty {duty_id} on {day}")


async def remove_swap(session: AsyncSession, duty_id: int, day: date) -> None:
    """Undo a swap; nothing happens if there is none."""
    swap = await session.scalar(select(Swap).where(Swap.duty_id == duty_id, Swap.day == day))
    if swap is not None:
        await session.delete(swap)
        await session.commit()


def _spec(rule: Rule) -> RuleSpec:
    return RuleSpec(
        mode=rule.mode,
        person_id=rule.person_id,
        rotation=tuple(member.person_id for member in rule.rotation),
        period=rule.rotation_period,
        anchor=rule.anchor_date,
    )


async def schedule(session: AsyncSession, first: date, days: int) -> list[DayRead]:
    """Resolved slots for `days` consecutive days starting at `first`."""
    duties = list(await session.scalars(select(Duty).where(Duty.active.is_(True)).order_by(Duty.sort_order, Duty.id)))
    last = first + timedelta(days=days - 1)
    swaps = {
        (swap.duty_id, swap.day): swap.person_id
        for swap in await session.scalars(select(Swap).where(Swap.day >= first, Swap.day <= last))
    }
    active_ids = {person.id for person in await core_service.list_people(session)}
    result = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        slots = []
        for duty in duties:
            if day.weekday() not in mask_to_weekdays(duty.weekdays):
                continue
            rule = next((r for r in duty.rules if r.weekday == day.weekday()), None)
            assignment = resolve(_spec(rule) if rule else None, swaps.get((duty.id, day)), day, active_ids)
            slots.append(
                SlotRead(
                    duty_id=duty.id,
                    duty_name=duty.name,
                    icon=duty.icon,
                    color=duty.color,
                    time_of_day=duty.time_of_day,
                    date=day,
                    source=assignment.source,
                    person_id=assignment.person_id,
                    warning=assignment.warning,
                    for_person_id=duty.for_person_id,
                )
            )
        result.append(DayRead(date=day, slots=slots))
    return result


async def week(session: AsyncSession, day: date) -> WeekRead:
    """The resolved week containing `day`."""
    start = week_start(day)
    return WeekRead(start=start, days=await schedule(session, start, DAYS_PER_WEEK))


async def duty_stats(session: AsyncSession, first: date, last: date) -> list[DutyStat]:
    """Planned assignments (rules and swaps) per duty and person from `first` to `last`, in duty order."""
    days = await schedule(session, first, (last - first).days + 1)
    stats: dict[int, DutyStat] = {}
    for day in days:
        for slot in day.slots:
            stat = stats.setdefault(
                slot.duty_id, DutyStat(duty_id=slot.duty_id, duty_name=slot.duty_name, color=slot.color, counts={})
            )
            if slot.person_id is None:
                stat.open += 1
            else:
                stat.counts[slot.person_id] = stat.counts.get(slot.person_id, 0) + 1
    return list(stats.values())


async def _count(session: AsyncSession, query: Select) -> int:
    return await session.scalar(select(func.count()).select_from(query.subquery())) or 0


async def count_person_data(session: AsyncSession, person_id: int) -> dict[str, int]:
    """Duties for, rules and swaps naming one person."""
    rules = select(Rule.id).where(
        or_(
            Rule.person_id == person_id,
            Rule.id.in_(select(RotationMember.rule_id).where(RotationMember.person_id == person_id)),
        )
    )
    return {
        "rhythm.data.duties": await _count(session, select(Duty.id).where(Duty.for_person_id == person_id)),
        "rhythm.data.rules": await _count(session, rules),
        "rhythm.data.swaps": await _count(session, select(Swap.id).where(Swap.person_id == person_id)),
    }


async def delete_person_data(session: AsyncSession, person_id: int) -> None:
    """Delete duties for and swaps of one person, and take them out of all rules; the caller commits."""
    duties = select(Duty.id).where(Duty.for_person_id == person_id)
    rules = select(Rule.id).where(Rule.duty_id.in_(duties))
    await session.execute(delete(RotationMember).where(RotationMember.rule_id.in_(rules)))
    await session.execute(delete(Rule).where(Rule.duty_id.in_(duties)))
    await session.execute(delete(Swap).where(or_(Swap.person_id == person_id, Swap.duty_id.in_(duties))))
    await session.execute(delete(Duty).where(Duty.for_person_id == person_id))
    await session.execute(delete(RotationMember).where(RotationMember.person_id == person_id))
    await session.execute(update(Rule).where(Rule.person_id == person_id).values(person_id=None))
