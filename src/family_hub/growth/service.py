"""Business logic for growth measurements; the only place touching growth tables."""

import logging
import math
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.config import get_settings
from family_hub.core import service as core_service
from family_hub.core.schemas import PersonRead
from family_hub.errors import InvalidInputError
from family_hub.growth.metrics import Point, age_months
from family_hub.growth.models import UNITS, Measurement, MeasurementType
from family_hub.growth.reference import Reference, load_reference, z_to_percentile
from family_hub.growth.schemas import ImportedMeasurement, MeasurementRead, MeasurementWrite, TypeStatus

logger = logging.getLogger(__name__)

PLAUSIBLE_RANGES = {
    MeasurementType.WEIGHT: (0.3, 200.0),
    MeasurementType.LENGTH: (20.0, 250.0),
    MeasurementType.HEAD: (20.0, 70.0),
}


class NotFoundError(LookupError):
    """Raised when a measurement does not exist."""


class NotAChildError(ValueError):
    """Raised when growth data is requested for a person without child profile."""


def reference_for(person: PersonRead, measurement_type: MeasurementType) -> Reference | None:
    """Return the configured reference for a child's sex, or None."""
    if person.sex is None:
        return None
    return load_reference(get_settings().growth_reference_dir, measurement_type, person.sex)


async def _child(session: AsyncSession, person_id: int) -> PersonRead:
    person = await core_service.get_person(session, person_id)
    if person.birth_date is None or person.sex is None:
        raise NotAChildError(f"{person.name} has no child profile")
    return person


def _validate(data: MeasurementWrite, person: PersonRead) -> None:
    low, high = PLAUSIBLE_RANGES[data.type]
    if not low <= data.value <= high:
        raise InvalidInputError(
            "error.value_range", type=data.type.value, low=f"{low:g}", high=f"{high:g}", unit=UNITS[data.type]
        )
    if person.birth_date and data.measured_on < person.birth_date:
        raise InvalidInputError("error.before_birth")
    if data.measured_on > date.today():
        raise InvalidInputError("error.future_date")


def _read(measurement: Measurement, person: PersonRead) -> MeasurementRead:
    age = age_months(person.birth_date, measurement.measured_on) if person.birth_date else 0.0
    reference = reference_for(person, measurement.type)
    z = reference.z_score(measurement.value, age) if reference and age <= reference.max_age else None
    if z is not None and not math.isfinite(z):
        z = None
    return MeasurementRead(
        id=measurement.id,
        person_id=measurement.person_id,
        type=measurement.type,
        value=measurement.value,
        unit=UNITS[measurement.type],
        measured_on=measurement.measured_on,
        official=measurement.official,
        age_months=age,
        note=measurement.note,
        z=z,
        percentile=z_to_percentile(z) if z is not None else None,
    )


def to_points(measurements: list[MeasurementRead]) -> list[Point]:
    """Reduce measurements to velocity input."""
    return [Point(measured_on=m.measured_on, age_months=m.age_months, value=m.value) for m in measurements]


async def list_measurements(
    session: AsyncSession, person_id: int, measurement_type: MeasurementType | None = None
) -> list[MeasurementRead]:
    """List a child's measurements, oldest first.

    Raises:
        core_service.PersonNotFoundError: If the person does not exist.
        NotAChildError: If the person has no child profile.
    """
    person = await _child(session, person_id)
    query = select(Measurement).where(Measurement.person_id == person_id)
    if measurement_type is not None:
        query = query.where(Measurement.type == measurement_type)
    query = query.order_by(Measurement.measured_on, Measurement.id)
    return [_read(m, person) for m in await session.scalars(query)]


async def add_measurements(session: AsyncSession, items: list[MeasurementWrite]) -> list[MeasurementRead]:
    """Add measurements in one transaction.

    Raises:
        core_service.PersonNotFoundError: If a person does not exist.
        NotAChildError: If a person has no child profile.
        ValueError: If a value or date is implausible.
    """
    created = []
    for item in items:
        person = await _child(session, item.person_id)
        _validate(item, person)
        measurement = Measurement(
            person_id=item.person_id,
            type=item.type,
            value=item.value,
            measured_on=item.measured_on,
            official=item.official,
            note=(item.note or "").strip() or None,
        )
        session.add(measurement)
        created.append((measurement, person))
    await session.commit()
    logger.info(f"Added {len(created)} measurements")
    return [_read(m, person) for m, person in created]


async def update_measurement(session: AsyncSession, measurement_id: int, data: MeasurementWrite) -> MeasurementRead:
    """Replace a measurement's value, date, type, official flag and note.

    Raises:
        NotFoundError: If the measurement does not exist.
        ValueError: If a value or date is implausible.
    """
    measurement = await session.get(Measurement, measurement_id)
    if measurement is None:
        raise NotFoundError(f"Measurement {measurement_id} not found")
    person = await _child(session, measurement.person_id)
    _validate(data, person)
    measurement.type = data.type
    measurement.value = data.value
    measurement.measured_on = data.measured_on
    measurement.official = data.official
    measurement.note = (data.note or "").strip() or None
    await session.commit()
    return _read(measurement, person)


async def delete_measurement(session: AsyncSession, measurement_id: int) -> None:
    """Delete a measurement.

    Raises:
        NotFoundError: If the measurement does not exist.
    """
    measurement = await session.get(Measurement, measurement_id)
    if measurement is None:
        raise NotFoundError(f"Measurement {measurement_id} not found")
    await session.delete(measurement)
    await session.commit()
    logger.info(f"Deleted measurement {measurement_id}")


async def status(session: AsyncSession, person_id: int) -> list[TypeStatus]:
    """Latest and previous measurement per type.

    Raises:
        NotAChildError: If the person has no child profile.
    """
    measurements = await list_measurements(session, person_id)
    result = []
    for measurement_type in MeasurementType:
        own = [m for m in measurements if m.type is measurement_type]
        if own:
            result.append(TypeStatus(type=measurement_type, latest=own[-1], previous=own[-2] if len(own) > 1 else None))
    return result


async def export_all(session: AsyncSession) -> list[MeasurementRead]:
    """Every measurement of every child."""
    result = []
    for child in await core_service.list_children(session):
        result.extend(await list_measurements(session, child.id))
    return result


async def import_measurements(session: AsyncSession, items: list[ImportedMeasurement], *, dry_run: bool) -> list[str]:
    """Insert imported measurements in one transaction, skipping refs that already exist.

    Returns:
        The refs that were (or, in a dry run, would be) imported.

    Raises:
        NotAChildError: If a mapped person has no child profile.
        ValueError: If a value or date is implausible.
    """
    existing = set(await session.scalars(select(Measurement.import_ref).where(Measurement.import_ref.is_not(None))))
    imported = []
    for item in items:
        data = item.measurement
        person = await _child(session, data.person_id)
        if item.import_ref in existing:
            continue
        _validate(data, person)
        session.add(
            Measurement(
                person_id=data.person_id,
                type=data.type,
                value=data.value,
                measured_on=data.measured_on,
                official=data.official,
                note=data.note,
                import_ref=item.import_ref,
            )
        )
        imported.append(item.import_ref)
    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    return imported


async def count_person_data(session: AsyncSession, person_id: int) -> dict[str, int]:
    """Measurements of one person."""
    count = await session.scalar(
        select(func.count()).select_from(Measurement).where(Measurement.person_id == person_id)
    )
    return {"growth.data.measurements": count or 0}


async def delete_person_data(session: AsyncSession, person_id: int) -> None:
    """Delete all measurements of one person; the caller commits."""
    await session.execute(delete(Measurement).where(Measurement.person_id == person_id))
