from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonWrite
from family_hub.fever import service
from family_hub.fever.schemas import EpisodeWrite, QuickReadingWrite, ReadingWrite
from family_hub.fever.thresholds import AgeGroup, Level


async def _child(session: AsyncSession) -> int:
    person = await core_service.create_person(
        session, PersonWrite(name="Ada", kind=PersonKind.CHILD, birth_date=date(2022, 3, 15), sex=Sex.FEMALE)
    )
    return person.id


async def test_episode_with_readings(session: AsyncSession) -> None:
    person_id = await _child(session)
    episode = await service.create_episode(session, EpisodeWrite(person_id=person_id, label="Grippe"))

    await service.add_reading(session, episode.id, ReadingWrite(temperature=39.1, measured_at=datetime(2026, 1, 2, 8)))
    await service.add_reading(session, episode.id, ReadingWrite(temperature=37.0, measured_at=datetime(2026, 1, 1, 20)))
    detail = await service.get_episode(session, episode.id)

    assert detail.episode.thresholds.age_group is AgeGroup.CHILD
    assert [r.temperature for r in detail.readings] == [37.0, 39.1]
    assert [r.level for r in detail.readings] == [Level.NORMAL, Level.FEVER]
    assert detail.episode.last_reading is not None
    assert detail.episode.last_reading.temperature == 39.1
    assert detail.episode.max_temperature == 39.1


async def test_naive_times_are_local(session: AsyncSession) -> None:
    person_id = await _child(session)
    episode = await service.create_episode(session, EpisodeWrite(person_id=person_id, label="x"))

    reading = await service.add_reading(
        session, episode.id, ReadingWrite(temperature=38.0, measured_at=datetime(2026, 7, 1, 12))
    )

    assert reading.measured_at == datetime(2026, 7, 1, 10, tzinfo=UTC)


async def test_temperature_range(session: AsyncSession) -> None:
    person_id = await _child(session)
    episode = await service.create_episode(session, EpisodeWrite(person_id=person_id, label="x"))

    with pytest.raises(ValueError, match="between"):
        await service.add_reading(session, episode.id, ReadingWrite.model_construct(temperature=46.0))


async def test_quick_add_reuses_open_episode(session: AsyncSession) -> None:
    person_id = await _child(session)

    first = await service.quick_add_reading(session, QuickReadingWrite(person_id=person_id, temperature=38.4))
    second = await service.quick_add_reading(session, QuickReadingWrite(person_id=person_id, temperature=38.9))
    await service.set_closed(session, first.episode_id, closed=True)
    third = await service.quick_add_reading(session, QuickReadingWrite(person_id=person_id, temperature=37.9))

    assert first.episode_id == second.episode_id
    assert third.episode_id != first.episode_id
    assert len(await service.list_episodes(session, open_only=True)) == 1


async def test_delete_episode(session: AsyncSession) -> None:
    person_id = await _child(session)
    reading = await service.quick_add_reading(session, QuickReadingWrite(person_id=person_id, temperature=38.4))

    await service.delete_episode(session, reading.episode_id)

    with pytest.raises(service.NotFoundError):
        await service.get_episode(session, reading.episode_id)


async def test_csv(session: AsyncSession) -> None:
    person_id = await _child(session)
    reading = await service.quick_add_reading(
        session, QuickReadingWrite(person_id=person_id, temperature=38.4, measured_at=datetime(2026, 1, 1, 8), note="a")
    )

    csv = service.readings_csv(await service.get_episode(session, reading.episode_id))

    assert csv.splitlines()[1] == "2026-01-01 08:00;38.4;elevated;;a"
