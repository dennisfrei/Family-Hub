"""DTOs for the core API and service layer."""

from datetime import date

from pydantic import BaseModel

from family_hub.core.models import DEFAULT_COLOR, PersonKind, Sex


class PersonWrite(BaseModel):
    """Data to create or replace a person."""

    name: str
    kind: PersonKind
    color: str = DEFAULT_COLOR
    birth_date: date | None = None
    sex: Sex | None = None


class PersonRead(BaseModel):
    """A person as returned by the API."""

    id: int
    name: str
    kind: PersonKind
    color: str
    active: bool
    birth_date: date | None = None
    sex: Sex | None = None


class ChildRead(BaseModel):
    """An active child with the current age in months."""

    id: int
    name: str
    color: str
    birth_date: date
    sex: Sex
    age_months: int
