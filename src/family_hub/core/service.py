"""Business logic for people and children; the only place touching core tables."""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core.models import ChildProfile, Person, PersonKind, Sex
from family_hub.core.schemas import ChildRead, PersonRead, PersonWrite
from family_hub.errors import InvalidInputError

logger = logging.getLogger(__name__)


class PersonNotFoundError(LookupError):
    """Raised when a person id does not exist."""


def age_in_months(birth_date: date, on: date) -> int:
    """Return the completed months between `birth_date` and `on`."""
    months = (on.year - birth_date.year) * 12 + on.month - birth_date.month
    if on.day < birth_date.day:
        months -= 1
    return max(months, 0)


def _child_profile(data: PersonWrite) -> tuple[date, Sex] | None:
    if data.kind is not PersonKind.CHILD:
        return None
    if data.birth_date is None or data.sex is None:
        raise InvalidInputError("error.child_profile_required")
    return data.birth_date, data.sex


def _validate(data: PersonWrite) -> None:
    if not data.name.strip():
        raise InvalidInputError("error.name_required")
    _child_profile(data)


def _apply(person: Person, data: PersonWrite) -> None:
    person.name = data.name.strip()
    person.kind = data.kind
    person.color = data.color
    profile = _child_profile(data)
    if profile is None:
        person.child_profile = None
    elif person.child_profile is None:
        person.child_profile = ChildProfile(birth_date=profile[0], sex=profile[1])
    else:
        person.child_profile.birth_date, person.child_profile.sex = profile


def to_read(person: Person) -> PersonRead:
    """Convert a person model to its DTO."""
    profile = person.child_profile
    return PersonRead(
        id=person.id,
        name=person.name,
        kind=person.kind,
        color=person.color,
        active=person.active,
        birth_date=profile.birth_date if profile else None,
        sex=profile.sex if profile else None,
    )


async def list_people(session: AsyncSession, *, include_inactive: bool = False) -> list[PersonRead]:
    """List people ordered by kind and name."""
    query = select(Person).order_by(Person.kind, Person.name)
    if not include_inactive:
        query = query.where(Person.active.is_(True))
    result = await session.scalars(query)
    return [to_read(person) for person in result]


async def list_children(session: AsyncSession, *, on: date | None = None) -> list[ChildRead]:
    """List active children, oldest first, with their age on `on` (default today)."""
    on = on or date.today()
    query = (
        select(Person)
        .join(Person.child_profile)
        .where(Person.active.is_(True), Person.kind == PersonKind.CHILD)
        .order_by(ChildProfile.birth_date)
    )
    children = []
    for person in await session.scalars(query):
        profile = person.child_profile
        if profile is None:
            continue
        children.append(
            ChildRead(
                id=person.id,
                name=person.name,
                color=person.color,
                birth_date=profile.birth_date,
                sex=profile.sex,
                age_months=age_in_months(profile.birth_date, on),
            )
        )
    return children


async def get_person(session: AsyncSession, person_id: int) -> PersonRead:
    """Return one person.

    Raises:
        PersonNotFoundError: If the id does not exist.
    """
    return to_read(await _load(session, person_id))


async def create_person(session: AsyncSession, data: PersonWrite) -> PersonRead:
    """Create a person (and child profile for children).

    Raises:
        ValueError: If the data is incomplete.
    """
    _validate(data)
    person = Person(active=True)
    _apply(person, data)
    session.add(person)
    await session.commit()
    logger.info(f"Created person {person.id}")
    return to_read(person)


async def update_person(session: AsyncSession, person_id: int, data: PersonWrite) -> PersonRead:
    """Replace a person's data.

    Raises:
        PersonNotFoundError: If the id does not exist.
        ValueError: If the data is incomplete.
    """
    _validate(data)
    person = await _load(session, person_id)
    _apply(person, data)
    await session.commit()
    logger.info(f"Updated person {person_id}")
    return to_read(person)


async def set_active(session: AsyncSession, person_id: int, *, active: bool) -> PersonRead:
    """Activate or deactivate a person.

    Raises:
        PersonNotFoundError: If the id does not exist.
    """
    person = await _load(session, person_id)
    person.active = active
    await session.commit()
    logger.info(f"Set person {person_id} active={active}")
    return to_read(person)


async def delete_person(session: AsyncSession, person_id: int) -> None:
    """Delete a person and the child profile; the caller removes module data first and commits.

    Raises:
        PersonNotFoundError: If the id does not exist.
    """
    await session.delete(await _load(session, person_id))
    await session.flush()


async def _load(session: AsyncSession, person_id: int) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise PersonNotFoundError(f"Person {person_id} not found")
    return person
