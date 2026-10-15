"""Business logic for journal entries and tags; the only place touching time capsule tables."""

import logging
from datetime import date

from sqlalchemy import Select, delete, extract, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.core.schemas import PersonRead
from family_hub.errors import InvalidInputError
from family_hub.time_capsule.models import Entry, EntryPerson, EntryType, Tag, entry_tag
from family_hub.time_capsule.schemas import EntryChild, EntryFilter, EntryRead, EntryWrite, TagRead

logger = logging.getLogger(__name__)

MAX_TAG_LENGTH = 50


class NotFoundError(LookupError):
    """Raised when an entry does not exist."""


def normalize_tags(tags: list[str]) -> list[str]:
    """Strip `#` and whitespace, drop empty and case-insensitive duplicates."""
    result: dict[str, str] = {}
    for tag in tags:
        name = tag.strip().lstrip("#").strip()[:MAX_TAG_LENGTH]
        if name and name.lower() not in result:
            result[name.lower()] = name
    return list(result.values())


async def _people(session: AsyncSession) -> dict[int, PersonRead]:
    return {p.id: p for p in await core_service.list_people(session, include_inactive=True)}


def _read(entry: Entry, people: dict[int, PersonRead]) -> EntryRead:
    children = []
    for link in entry.people:
        person = people.get(link.person_id)
        if person is None:
            continue
        age = core_service.age_in_months(person.birth_date, entry.day) if person.birth_date else None
        children.append(EntryChild(person_id=person.id, name=person.name, color=person.color, age_months=age))
    children.sort(key=lambda c: c.name)
    author = people.get(entry.author_id) if entry.author_id else None
    return EntryRead(
        id=entry.id,
        text=entry.text,
        type=entry.type,
        date=entry.day,
        children=children,
        tags=sorted((tag.name for tag in entry.tags), key=str.lower),
        created_at=entry.created_at,
        context=entry.context,
        author_id=entry.author_id,
        author_name=author.name if author else None,
    )


async def _validate(session: AsyncSession, data: EntryWrite) -> None:
    if not data.text.strip():
        raise InvalidInputError("error.text_required")
    if not data.person_ids:
        raise InvalidInputError("error.child_required")
    if data.date and data.date > date.today():
        raise InvalidInputError("error.future_date")
    person_ids = set(data.person_ids)
    if data.author_id is not None:
        person_ids.add(data.author_id)
    for person_id in person_ids:
        await core_service.get_person(session, person_id)


async def _tags(session: AsyncSession, names: list[str]) -> list[Tag]:
    result = []
    for name in normalize_tags(names):
        tag = await session.scalar(select(Tag).where(func.lower(Tag.name) == name.lower()))
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
        result.append(tag)
    return result


async def _drop_unused_tags(session: AsyncSession) -> None:
    used = select(entry_tag.c.tag_id)
    for tag in await session.scalars(select(Tag).where(Tag.id.not_in(used))):
        await session.delete(tag)


def _apply_filter(query: Select[Entry], filters: EntryFilter) -> Select[Entry]:
    if filters.person_id is not None:
        query = query.where(Entry.people.any(EntryPerson.person_id == filters.person_id))
    if filters.type is not None:
        query = query.where(Entry.type == filters.type)
    if filters.tag:
        query = query.where(Entry.tags.any(func.lower(Tag.name) == filters.tag.lower()))
    if filters.year is not None:
        query = query.where(Entry.day >= date(filters.year, 1, 1), Entry.day <= date(filters.year, 12, 31))
    if filters.query:
        pattern = f"%{filters.query.lower()}%"
        query = query.where(
            or_(func.lower(Entry.text).like(pattern), func.lower(func.coalesce(Entry.context, "")).like(pattern))
        )
    return query


async def list_entries(session: AsyncSession, filters: EntryFilter | None = None) -> list[EntryRead]:
    """List entries, newest first."""
    query = _apply_filter(select(Entry), filters or EntryFilter()).order_by(Entry.day.desc(), Entry.id.desc())
    people = await _people(session)
    return [_read(entry, people) for entry in await session.scalars(query)]


async def get_entry(session: AsyncSession, entry_id: int) -> EntryRead:
    """Return one entry.

    Raises:
        NotFoundError: If the entry does not exist.
    """
    return _read(await _load(session, entry_id), await _people(session))


async def _load(session: AsyncSession, entry_id: int) -> Entry:
    entry = await session.get(Entry, entry_id)
    if entry is None:
        raise NotFoundError(f"Entry {entry_id} not found")
    return entry


async def create_entry(session: AsyncSession, data: EntryWrite) -> EntryRead:
    """Create an entry.

    Raises:
        ValueError: If text or children are missing or the date is in the future.
        core_service.PersonNotFoundError: If a person does not exist.
    """
    await _validate(session, data)
    entry = Entry(
        text=data.text.strip(),
        type=data.type,
        day=data.date or date.today(),
        context=(data.context or "").strip() or None,
        author_id=data.author_id,
        people=[EntryPerson(person_id=person_id) for person_id in dict.fromkeys(data.person_ids)],
        tags=await _tags(session, data.tags),
    )
    session.add(entry)
    await session.commit()
    logger.info(f"Created entry {entry.id}")
    return _read(entry, await _people(session))


async def update_entry(session: AsyncSession, entry_id: int, data: EntryWrite) -> EntryRead:
    """Replace an entry's content; the author is kept unless a new one is given.

    Raises:
        NotFoundError: If the entry does not exist.
        ValueError: If text or children are missing or the date is in the future.
    """
    await _validate(session, data)
    entry = await _load(session, entry_id)
    entry.text = data.text.strip()
    entry.type = data.type
    entry.day = data.date or entry.day
    entry.context = (data.context or "").strip() or None
    entry.author_id = data.author_id or entry.author_id
    entry.people = [EntryPerson(entry_id=entry.id, person_id=person_id) for person_id in dict.fromkeys(data.person_ids)]
    entry.tags = await _tags(session, data.tags)
    await session.flush()
    await _drop_unused_tags(session)
    await session.commit()
    return _read(entry, await _people(session))


async def delete_entry(session: AsyncSession, entry_id: int) -> None:
    """Delete an entry.

    Raises:
        NotFoundError: If the entry does not exist.
    """
    await session.delete(await _load(session, entry_id))
    await session.flush()
    await _drop_unused_tags(session)
    await session.commit()
    logger.info(f"Deleted entry {entry_id}")


async def on_this_day(session: AsyncSession, day: date) -> list[EntryRead]:
    """Entries from the same calendar day in earlier years, newest first."""
    query = (
        select(Entry)
        .where(
            extract("month", Entry.day) == day.month,
            extract("day", Entry.day) == day.day,
            Entry.day < date(day.year, 1, 1),
        )
        .order_by(Entry.day.desc())
    )
    people = await _people(session)
    return [_read(entry, people) for entry in await session.scalars(query)]


async def milestones(session: AsyncSession, person_id: int | None = None) -> list[EntryRead]:
    """Milestones, oldest first."""
    entries = await list_entries(session, EntryFilter(person_id=person_id, type=EntryType.MILESTONE))
    return list(reversed(entries))


async def list_tags(session: AsyncSession) -> list[TagRead]:
    """Tags with entry counts, most used first."""
    query = (
        select(Tag.name, func.count(entry_tag.c.entry_id))
        .join(entry_tag, entry_tag.c.tag_id == Tag.id)
        .group_by(Tag.name)
        .order_by(func.count(entry_tag.c.entry_id).desc(), Tag.name)
    )
    return [TagRead(name=name, count=count) for name, count in await session.execute(query)]


async def years(session: AsyncSession) -> list[int]:
    """Years that have entries, newest first."""
    days = await session.scalars(select(Entry.day))
    return sorted({day.year for day in days}, reverse=True)


def _sole_entries(person_id: int) -> Select:
    others = select(EntryPerson.entry_id).where(EntryPerson.person_id != person_id)
    return select(EntryPerson.entry_id).where(EntryPerson.person_id == person_id, EntryPerson.entry_id.not_in(others))


async def count_person_data(session: AsyncSession, person_id: int) -> dict[str, int]:
    """Entries only about one person, and shared entries that keep the other children."""
    linked = await session.scalar(
        select(func.count()).select_from(EntryPerson).where(EntryPerson.person_id == person_id)
    )
    sole = await session.scalar(select(func.count()).select_from(_sole_entries(person_id).subquery()))
    return {"tc.data.entries": sole or 0, "tc.data.shared": (linked or 0) - (sole or 0)}


async def delete_person_data(session: AsyncSession, person_id: int) -> None:
    """Delete entries only about one person and unlink the rest; the caller commits."""
    sole = list(await session.scalars(_sole_entries(person_id)))
    if sole:
        await session.execute(delete(entry_tag).where(entry_tag.c.entry_id.in_(sole)))
        await session.execute(delete(EntryPerson).where(EntryPerson.entry_id.in_(sole)))
        await session.execute(delete(Entry).where(Entry.id.in_(sole)))
    await session.execute(delete(EntryPerson).where(EntryPerson.person_id == person_id))
    await session.execute(update(Entry).where(Entry.author_id == person_id).values(author_id=None))
