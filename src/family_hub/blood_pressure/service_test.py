from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.blood_pressure import service
from family_hub.blood_pressure.levels import Level
from family_hub.blood_pressure.schemas import Measurement, ReadingWrite
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.schemas import PersonWrite


async def _adult(session: AsyncSession, name: str = "Alex") -> int:
    return (await core_service.create_person(session, PersonWrite(name=name, kind=PersonKind.ADULT))).id


async def test_readings_newest_first(session: AsyncSession) -> None:
    person_id = await _adult(session)
    other_id = await _adult(session, "Sam")
    await service.add_reading(
        session, ReadingWrite(person_id=person_id, systolic=118, diastolic=76, measured_at=datetime(2026, 7, 1, 8))
    )
    await service.add_reading(
        session,
        ReadingWrite(person_id=person_id, systolic=142, diastolic=88, pulse=70, measured_at=datetime(2026, 7, 2, 8)),
    )
    await service.add_reading(session, ReadingWrite(person_id=other_id, systolic=120, diastolic=80))

    readings = await service.list_readings(session, person_id=person_id)

    assert [(r.systolic, r.level) for r in readings] == [(142, Level.HIGH), (118, Level.NORMAL)]
    assert readings[0].pulse == 70
    assert readings[1].measured_at == datetime(2026, 7, 1, 6, tzinfo=UTC)
    assert len(await service.list_readings(session, person_id=person_id, limit=1)) == 1


@pytest.mark.parametrize(
    "measurement",
    [
        Measurement(systolic=300, diastolic=80),
        Measurement(systolic=120, diastolic=10),
        Measurement(systolic=120, diastolic=80, pulse=500),
        Measurement(systolic=80, diastolic=120),
    ],
)
def test_implausible_values(measurement: Measurement) -> None:
    with pytest.raises(ValueError, match="must be"):
        service.validate(measurement)


async def test_unknown_person(session: AsyncSession) -> None:
    with pytest.raises(core_service.PersonNotFoundError):
        await service.add_reading(session, ReadingWrite(person_id=99, systolic=120, diastolic=80))


async def test_add_readings_saves_all_or_none(session: AsyncSession) -> None:
    person_id = await _adult(session)
    good = ReadingWrite(person_id=person_id, systolic=128, diastolic=82, measured_at=datetime(2026, 7, 1, 8))
    bad = ReadingWrite(person_id=person_id, systolic=80, diastolic=120)

    with pytest.raises(ValueError, match="must be"):
        await service.add_readings(session, [good, bad])
    assert await service.list_readings(session) == []

    saved = await service.add_readings(session, [good, good.model_copy(update={"systolic": 135})])

    assert [reading.systolic for reading in saved] == [128, 135]
    assert len(await service.list_readings(session, person_id=person_id)) == 2


async def test_paging(session: AsyncSession) -> None:
    person_id = await _adult(session)
    await service.add_readings(
        session,
        [
            ReadingWrite(person_id=person_id, systolic=110 + day, diastolic=70, measured_at=datetime(2026, 7, day, 8))
            for day in range(1, 6)
        ],
    )

    page = await service.list_readings(session, person_id=person_id, limit=2, offset=2)

    assert [reading.systolic for reading in page] == [113, 112]
    assert await service.count_readings(session, person_id) == 5
    assert len(await service.list_readings(session, person_id=person_id, since=datetime(2026, 7, 4))) == 2


async def test_delete_reading(session: AsyncSession) -> None:
    person_id = await _adult(session)
    reading = await service.add_reading(session, ReadingWrite(person_id=person_id, systolic=120, diastolic=80))

    await service.delete_reading(session, reading.id)

    assert await service.list_readings(session) == []
    with pytest.raises(service.NotFoundError):
        await service.delete_reading(session, reading.id)


async def test_person_data(session: AsyncSession) -> None:
    person_id = await _adult(session)
    await service.add_reading(session, ReadingWrite(person_id=person_id, systolic=120, diastolic=80))

    assert await service.count_person_data(session, person_id) == {"bp.data.readings": 1}
    await service.delete_person_data(session, person_id)
    await session.commit()

    assert await service.count_person_data(session, person_id) == {"bp.data.readings": 0}
