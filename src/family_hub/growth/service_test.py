from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonWrite
from family_hub.growth import service
from family_hub.growth.conftest import value_at
from family_hub.growth.metrics import age_months
from family_hub.growth.models import MeasurementType
from family_hub.growth.schemas import ImportedMeasurement, MeasurementWrite

BIRTH = date(2022, 3, 15)


async def _child(session: AsyncSession) -> int:
    person = await core_service.create_person(
        session, PersonWrite(name="Ada", kind=PersonKind.CHILD, birth_date=BIRTH, sex=Sex.FEMALE)
    )
    return person.id


def _length(person_id: int, day: date, value: float, official: bool = True) -> MeasurementWrite:
    return MeasurementWrite(
        person_id=person_id, type=MeasurementType.LENGTH, value=value, measured_on=day, official=official
    )


async def test_percentile_with_reference(session: AsyncSession, reference_dir: Path) -> None:
    person_id = await _child(session)
    day = date(2024, 3, 15)
    value = value_at(age_months(BIRTH, day), 1.281552)

    [created] = await service.add_measurements(session, [_length(person_id, day, value)])

    assert created.percentile == pytest.approx(90.0, abs=0.5)


async def test_without_reference_no_percentile(session: AsyncSession) -> None:
    person_id = await _child(session)

    [created] = await service.add_measurements(session, [_length(person_id, date(2024, 3, 15), 90.0)])

    assert created.percentile is None
    assert created.z is None


async def test_status(session: AsyncSession) -> None:
    person_id = await _child(session)
    await service.add_measurements(
        session, [_length(person_id, date(2024, 1, 1), 88.0), _length(person_id, date(2024, 6, 1), 92.0)]
    )

    [status] = await service.status(session, person_id)

    assert status.latest.value == 92.0
    assert status.previous is not None and status.previous.value == 88.0


@pytest.mark.parametrize(
    ("value", "day", "message"),
    [(5.0, date(2024, 1, 1), "between"), (90.0, date(2020, 1, 1), "birth"), (90.0, date(2999, 1, 1), "future")],
)
async def test_validation(session: AsyncSession, value: float, day: date, message: str) -> None:
    person_id = await _child(session)

    with pytest.raises(ValueError, match=message):
        await service.add_measurements(session, [_length(person_id, day, value)])


async def test_adult_rejected(session: AsyncSession) -> None:
    adult = await core_service.create_person(session, PersonWrite(name="Alex", kind=PersonKind.ADULT))

    with pytest.raises(service.NotAChildError):
        await service.list_measurements(session, adult.id)


async def test_import_idempotent(session: AsyncSession) -> None:
    person_id = await _child(session)
    items = [ImportedMeasurement(import_ref="kiggs-plot:a", measurement=_length(person_id, date(2024, 1, 1), 88.0))]

    assert await service.import_measurements(session, items, dry_run=True) == ["kiggs-plot:a"]
    assert await service.list_measurements(session, person_id) == []
    assert await service.import_measurements(session, items, dry_run=False) == ["kiggs-plot:a"]
    assert await service.import_measurements(session, items, dry_run=False) == []
    assert len(await service.list_measurements(session, person_id)) == 1
