"""DTOs for the growth API and service layer."""

from datetime import date

from pydantic import BaseModel

from family_hub.growth.models import MeasurementType


class MeasurementWrite(BaseModel):
    """A new measurement; value in kg (weight) or cm (length, head)."""

    person_id: int
    type: MeasurementType
    value: float
    measured_on: date
    official: bool = True
    note: str | None = None


class MeasurementRead(BaseModel):
    """A measurement with age, SDS and percentile (None without reference data)."""

    id: int
    person_id: int
    type: MeasurementType
    value: float
    unit: str
    measured_on: date
    official: bool
    age_months: float
    note: str | None = None
    z: float | None = None
    percentile: float | None = None


class TypeStatus(BaseModel):
    """Latest measurement of a type and the one before."""

    type: MeasurementType
    latest: MeasurementRead
    previous: MeasurementRead | None = None


class ImportedMeasurement(BaseModel):
    """A measurement from another app; `import_ref` makes re-imports idempotent."""

    import_ref: str
    measurement: MeasurementWrite
