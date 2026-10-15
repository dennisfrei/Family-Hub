"""Illness episodes and temperature readings (schema `fever`)."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_hub.db import Base

SCHEMA = "fever"


class Method(StrEnum):
    """How the temperature was measured."""

    EAR = "ear"
    RECTAL = "rectal"
    FOREHEAD = "forehead"
    ARMPIT = "armpit"
    ORAL = "oral"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Episode(Base):
    """One illness of one person; open while `ended_at` is empty."""

    __tablename__ = "episode"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("core.person.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    import_ref: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    readings: Mapped[list["Reading"]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="Reading.measured_at",
        lazy="selectin",
    )


class Reading(Base):
    """A single temperature measurement."""

    __tablename__ = "reading"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.episode.id", ondelete="CASCADE"), index=True)
    temperature: Mapped[float] = mapped_column(Float)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    method: Mapped[Method | None] = mapped_column(
        Enum(Method, native_enum=False, length=16, values_callable=lambda members: [m.value for m in members])
    )
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    episode: Mapped[Episode] = relationship(back_populates="readings")
