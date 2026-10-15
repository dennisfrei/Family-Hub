"""People, child profiles and API tokens, shared by all modules (schema `core`)."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_hub.db import Base

SCHEMA = "core"
DEFAULT_COLOR = "#607d8b"


class PersonKind(StrEnum):
    """Whether a person is an adult or a child."""

    ADULT = "adult"
    CHILD = "child"


class Sex(StrEnum):
    """Sex used for growth percentiles."""

    FEMALE = "female"
    MALE = "male"


def _str_enum(enum_cls: type[StrEnum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=16, values_callable=lambda members: [m.value for m in members])


class Person(Base):
    """A family member; every module references `core.person.id`."""

    __tablename__ = "person"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[PersonKind] = mapped_column(_str_enum(PersonKind))
    color: Mapped[str] = mapped_column(String(7), default=DEFAULT_COLOR)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    child_profile: Mapped["ChildProfile | None"] = relationship(
        back_populates="person", lazy="selectin", cascade="all, delete-orphan"
    )


class ChildProfile(Base):
    """Child-only data; age is always derived from `birth_date`."""

    __tablename__ = "child_profile"
    __table_args__ = {"schema": SCHEMA}

    person_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.person.id", ondelete="CASCADE"), primary_key=True)
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[Sex] = mapped_column(_str_enum(Sex))

    person: Mapped[Person] = relationship(back_populates="child_profile")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ApiToken(Base):
    """An issued API token; only tokens listed here and not revoked are accepted."""

    __tablename__ = "api_token"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
