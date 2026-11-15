"""Business logic for blood pressure readings; the only place touching blood pressure tables."""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.blood_pressure.levels import level_of
from family_hub.blood_pressure.models import PressureReading
from family_hub.blood_pressure.schemas import (
    DIASTOLIC_RANGE,
    PULSE_RANGE,
    SYSTOLIC_RANGE,
    Measurement,
    ReadingRead,
    ReadingWrite,
)
from family_hub.core import service as core_service
from family_hub.errors import InvalidInputError
from family_hub.fever.service import to_utc

logger = logging.getLogger(__name__)

UNIT = "mmHg"
PULSE_UNIT = "bpm"


class NotFoundError(LookupError):
    """Raised when a reading does not exist."""


def _check_range(name: str, value: int, limits: tuple[int, int], unit: str) -> None:
    if not limits[0] <= value <= limits[1]:
        raise InvalidInputError("error.value_range", type=name, low=limits[0], high=limits[1], unit=unit)


def validate(measurement: Measurement) -> None:
    """Check that the values are plausible.

    Raises:
        InvalidInputError: If a value is out of range or systolic is not above diastolic.
    """
    _check_range("Systolic", measurement.systolic, SYSTOLIC_RANGE, UNIT)
    _check_range("Diastolic", measurement.diastolic, DIASTOLIC_RANGE, UNIT)
    if measurement.pulse is not None:
        _check_range("Pulse", measurement.pulse, PULSE_RANGE, PULSE_UNIT)
    if measurement.systolic <= measurement.diastolic:
        raise InvalidInputError("error.blood_pressure_order")


def _read(reading: PressureReading) -> ReadingRead:
    return ReadingRead(
        id=reading.id,
        person_id=reading.person_id,
        systolic=reading.systolic,
        diastolic=reading.diastolic,
        pulse=reading.pulse,
        measured_at=reading.measured_at,
        level=level_of(reading.systolic, reading.diastolic),
        note=reading.note,
    )


async def list_readings(
    session: AsyncSession,
    *,
    person_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
    since: datetime | None = None,
) -> list[ReadingRead]:
    """List readings, newest first; `offset` skips the newest ones, `since` drops older ones."""
    query = select(PressureReading).order_by(PressureReading.measured_at.desc(), PressureReading.id.desc())
    if person_id is not None:
        query = query.where(PressureReading.person_id == person_id)
    if since is not None:
        query = query.where(PressureReading.measured_at >= to_utc(since))
    if limit is not None:
        query = query.limit(limit)
    return [_read(reading) for reading in await session.scalars(query.offset(offset))]


async def count_readings(session: AsyncSession, person_id: int) -> int:
    """Number of readings of one person."""
    count = await session.scalar(
        select(func.count()).select_from(PressureReading).where(PressureReading.person_id == person_id)
    )
    return count or 0


async def add_reading(session: AsyncSession, data: ReadingWrite) -> ReadingRead:
    """Add a reading for a person.

    Raises:
        core_service.PersonNotFoundError: If the person does not exist.
        InvalidInputError: If the values are not plausible.
    """
    return (await add_readings(session, [data]))[0]


async def add_readings(session: AsyncSession, entries: list[ReadingWrite]) -> list[ReadingRead]:
    """Add several readings at once; nothing is saved if one of them is invalid.

    Raises:
        core_service.PersonNotFoundError: If a person does not exist.
        InvalidInputError: If the values of an entry are not plausible.
    """
    for data in entries:
        validate(data)
    for person_id in {data.person_id for data in entries}:
        await core_service.get_person(session, person_id)
    readings = [
        PressureReading(
            person_id=data.person_id,
            systolic=data.systolic,
            diastolic=data.diastolic,
            pulse=data.pulse,
            measured_at=to_utc(data.measured_at or datetime.now(UTC)),
            note=(data.note or "").strip() or None,
        )
        for data in entries
    ]
    session.add_all(readings)
    await session.commit()
    logger.info(f"Added {len(readings)} blood pressure readings")
    return [_read(reading) for reading in readings]


async def delete_reading(session: AsyncSession, reading_id: int) -> None:
    """Delete a reading.

    Raises:
        NotFoundError: If the reading does not exist.
    """
    reading = await session.get(PressureReading, reading_id)
    if reading is None:
        raise NotFoundError(f"Reading {reading_id} not found")
    await session.delete(reading)
    await session.commit()
    logger.info(f"Deleted blood pressure reading {reading_id}")


async def count_person_data(session: AsyncSession, person_id: int) -> dict[str, int]:
    """Readings of one person."""
    return {"bp.data.readings": await count_readings(session, person_id)}


async def delete_person_data(session: AsyncSession, person_id: int) -> None:
    """Delete all readings of one person; the caller commits."""
    await session.execute(delete(PressureReading).where(PressureReading.person_id == person_id))
