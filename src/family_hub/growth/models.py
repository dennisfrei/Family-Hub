"""Body measurements per person (schema `growth`)."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from family_hub.db import Base

SCHEMA = "growth"


class MeasurementType(StrEnum):
    """What was measured; values are stored in the type's unit."""

    WEIGHT = "weight"
    LENGTH = "length"
    HEAD = "head"


UNITS = {MeasurementType.WEIGHT: "kg", MeasurementType.LENGTH: "cm", MeasurementType.HEAD: "cm"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Measurement(Base):
    """One measured value; `official` marks measurements at the doctor's."""

    __tablename__ = "measurement"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("core.person.id"), index=True)
    type: Mapped[MeasurementType] = mapped_column(
        Enum(MeasurementType, native_enum=False, length=16, values_callable=lambda members: [m.value for m in members])
    )
    value: Mapped[float] = mapped_column(Float)
    measured_on: Mapped[date] = mapped_column(Date)
    official: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(500))
    import_ref: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
