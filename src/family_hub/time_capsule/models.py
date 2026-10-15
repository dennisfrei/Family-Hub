"""Journal entries with children and tags (schema `time_capsule`)."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_hub.db import Base

SCHEMA = "time_capsule"


class EntryType(StrEnum):
    """Kind of entry."""

    SAYING = "saying"
    MOMENT = "moment"
    MILESTONE = "milestone"


def _utcnow() -> datetime:
    return datetime.now(UTC)


entry_tag = Table(
    "entry_tag",
    Base.metadata,
    Column("entry_id", ForeignKey(f"{SCHEMA}.entry.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey(f"{SCHEMA}.tag.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)


class Entry(Base):
    """Something worth keeping about one or more children."""

    __tablename__ = "entry"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(String(500))
    type: Mapped[EntryType] = mapped_column(
        Enum(EntryType, native_enum=False, length=16, values_callable=lambda members: [m.value for m in members])
    )
    day: Mapped[date] = mapped_column("date", Date, index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("core.person.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    people: Mapped[list["EntryPerson"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    tags: Mapped[list["Tag"]] = relationship(secondary=entry_tag, lazy="selectin", order_by="Tag.name")


class EntryPerson(Base):
    """Link between an entry and a child it is about."""

    __tablename__ = "entry_person"
    __table_args__ = {"schema": SCHEMA}

    entry_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.entry.id", ondelete="CASCADE"), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("core.person.id"), primary_key=True, index=True)


class Tag(Base):
    """A free label."""

    __tablename__ = "tag"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
