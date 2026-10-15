"""DTOs for the fever API and service layer."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from family_hub.fever.models import Method
from family_hub.fever.thresholds import Level, Thresholds

MIN_TEMPERATURE = 35.0
MAX_TEMPERATURE = 45.0

Temperature = Annotated[float, Field(ge=MIN_TEMPERATURE, le=MAX_TEMPERATURE)]


class ReadingWrite(BaseModel):
    """A new reading; `measured_at` defaults to now."""

    temperature: Temperature
    measured_at: datetime | None = None
    method: Method | None = None
    note: str | None = None


class QuickReadingWrite(BaseModel):
    """A reading for a person, added to their open episode (created if needed)."""

    person_id: int
    temperature: Temperature
    measured_at: datetime | None = None
    method: Method | None = None
    note: str | None = None


class ReadingRead(BaseModel):
    """A reading with its classification."""

    id: int
    episode_id: int
    temperature: float
    measured_at: datetime
    level: Level
    method: Method | None = None
    note: str | None = None


class EpisodeWrite(BaseModel):
    """Data to create an episode."""

    person_id: int
    label: str
    description: str | None = None


class EpisodeUpdate(BaseModel):
    """Editable episode fields."""

    label: str
    description: str | None = None


class EpisodeRead(BaseModel):
    """Episode summary."""

    id: int
    person_id: int
    label: str
    started_at: datetime
    reading_count: int
    thresholds: Thresholds
    description: str | None = None
    ended_at: datetime | None = None
    max_temperature: float | None = None
    last_reading: ReadingRead | None = None


class EpisodeDetail(BaseModel):
    """Episode with all readings, oldest first."""

    episode: EpisodeRead
    readings: list[ReadingRead]


class ImportedEpisode(BaseModel):
    """A closed episode from another app; `import_ref` makes re-imports idempotent."""

    import_ref: str
    person_id: int
    label: str
    started_at: datetime
    ended_at: datetime
    readings: list[ReadingWrite]
    description: str | None = None
