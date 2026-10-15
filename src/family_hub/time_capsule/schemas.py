"""DTOs for the time capsule API and service layer."""

import datetime as dt
from datetime import datetime

from pydantic import BaseModel

from family_hub.time_capsule.models import EntryType


class EntryWrite(BaseModel):
    """A new or edited entry; `date` defaults to today."""

    text: str
    person_ids: list[int]
    type: EntryType = EntryType.MOMENT
    date: dt.date | None = None
    context: str | None = None
    tags: list[str] = []
    author_id: int | None = None


class EntryChild(BaseModel):
    """A child of an entry with the age on the entry date."""

    person_id: int
    name: str
    color: str
    age_months: int | None = None


class EntryRead(BaseModel):
    """A stored entry."""

    id: int
    text: str
    type: EntryType
    date: dt.date
    children: list[EntryChild]
    tags: list[str]
    created_at: datetime
    context: str | None = None
    author_id: int | None = None
    author_name: str | None = None


class EntryFilter(BaseModel):
    """Filters for listing entries; all optional and combined."""

    person_id: int | None = None
    type: EntryType | None = None
    tag: str | None = None
    year: int | None = None
    query: str | None = None


class TagRead(BaseModel):
    """A tag with its number of entries."""

    name: str
    count: int
