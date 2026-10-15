from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonWrite
from family_hub.time_capsule import service
from family_hub.time_capsule.models import EntryType
from family_hub.time_capsule.schemas import EntryFilter, EntryWrite


async def _children(session: AsyncSession) -> tuple[int, int]:
    ada = await core_service.create_person(
        session, PersonWrite(name="Ada", kind=PersonKind.CHILD, birth_date=date(2022, 3, 15), sex=Sex.FEMALE)
    )
    ben = await core_service.create_person(
        session, PersonWrite(name="Ben", kind=PersonKind.CHILD, birth_date=date(2024, 1, 1), sex=Sex.MALE)
    )
    return ada.id, ben.id


async def test_create_with_age_and_tags(session: AsyncSession) -> None:
    ada, ben = await _children(session)

    entry = await service.create_entry(
        session,
        EntryWrite(
            text="Warum regnet es?",
            person_ids=[ada, ben],
            type=EntryType.SAYING,
            date=date(2025, 7, 20),
            tags=["#lustig", "Lustig", " Kita "],
        ),
    )

    assert [(c.name, c.age_months) for c in entry.children] == [("Ada", 40), ("Ben", 18)]
    assert entry.tags == ["Kita", "lustig"]


async def test_filters(session: AsyncSession) -> None:
    ada, ben = await _children(session)
    await service.create_entry(
        session, EntryWrite(text="Erster Schritt", person_ids=[ben], type=EntryType.MILESTONE, date=date(2025, 1, 5))
    )
    await service.create_entry(
        session,
        EntryWrite(text="Sagt Banane", person_ids=[ada], type=EntryType.SAYING, date=date(2024, 6, 1), tags=["essen"]),
    )

    async def texts(filters: EntryFilter) -> list[str]:
        return [e.text for e in await service.list_entries(session, filters)]

    assert await texts(EntryFilter()) == ["Erster Schritt", "Sagt Banane"]
    assert await texts(EntryFilter(person_id=ada)) == ["Sagt Banane"]
    assert await texts(EntryFilter(type=EntryType.MILESTONE)) == ["Erster Schritt"]
    assert await texts(EntryFilter(tag="ESSEN")) == ["Sagt Banane"]
    assert await texts(EntryFilter(year=2025)) == ["Erster Schritt"]
    assert await texts(EntryFilter(query="banane")) == ["Sagt Banane"]
    assert await service.years(session) == [2025, 2024]


async def test_on_this_day_and_milestones(session: AsyncSession) -> None:
    ada, _ = await _children(session)
    await service.create_entry(session, EntryWrite(text="Damals", person_ids=[ada], date=date(2024, 10, 14)))
    await service.create_entry(session, EntryWrite(text="Anderer Tag", person_ids=[ada], date=date(2024, 10, 15)))
    await service.create_entry(
        session, EntryWrite(text="Läuft", person_ids=[ada], type=EntryType.MILESTONE, date=date(2023, 4, 1))
    )

    assert [e.text for e in await service.on_this_day(session, date(2026, 10, 14))] == ["Damals"]
    assert [e.text for e in await service.milestones(session, ada)] == ["Läuft"]


async def test_update_and_unused_tags_removed(session: AsyncSession) -> None:
    ada, _ = await _children(session)
    entry = await service.create_entry(session, EntryWrite(text="x", person_ids=[ada], tags=["alt"]))

    updated = await service.update_entry(session, entry.id, EntryWrite(text="y", person_ids=[ada], tags=["neu"]))

    assert updated.text == "y"
    assert [tag.name for tag in await service.list_tags(session)] == ["neu"]
    await service.delete_entry(session, entry.id)
    assert await service.list_tags(session) == []


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (EntryWrite(text=" ", person_ids=[1]), "Text"),
        (EntryWrite(text="x", person_ids=[]), "child"),
        (EntryWrite(text="x", person_ids=[1], date=date(2999, 1, 1)), "future"),
    ],
)
async def test_validation(session: AsyncSession, data: EntryWrite, message: str) -> None:
    await _children(session)

    with pytest.raises(ValueError, match=message):
        await service.create_entry(session, data)
