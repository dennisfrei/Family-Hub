"""Duties, weekday rules, rotations and swaps (schema `rhythm`)."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_hub.db import Base

SCHEMA = "rhythm"
DEFAULT_ICON = "task_alt"
DEFAULT_COLOR = "#64748b"


class TimeOfDay(StrEnum):
    """When in the day a duty happens."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class RuleMode(StrEnum):
    """How the assignee of a weekday is chosen."""

    FIXED = "fixed"
    ROTATION = "rotation"


class RotationPeriod(StrEnum):
    """How often a rotation moves to the next person."""

    DAILY = "daily"
    WEEKLY = "weekly"


def _enum(enum_cls: type[StrEnum]) -> Enum:
    return Enum(enum_cls, native_enum=False, length=16, values_callable=lambda members: [m.value for m in members])


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Duty(Base):
    """A coarse block of work; `weekdays` is a bitmask with Monday = bit 0."""

    __tablename__ = "duty"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(50), default=DEFAULT_ICON)
    color: Mapped[str] = mapped_column(String(7), default=DEFAULT_COLOR)
    time_of_day: Mapped[TimeOfDay] = mapped_column(_enum(TimeOfDay))
    weekdays: Mapped[int] = mapped_column(Integer)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    for_person_id: Mapped[int | None] = mapped_column(ForeignKey("core.person.id"))

    rules: Mapped[list["Rule"]] = relationship(
        back_populates="duty", cascade="all, delete-orphan", order_by="Rule.weekday", lazy="selectin"
    )


class Rule(Base):
    """Who normally does a duty on one weekday."""

    __tablename__ = "rule"
    __table_args__ = (UniqueConstraint("duty_id", "weekday"), {"schema": SCHEMA})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    duty_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.duty.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    mode: Mapped[RuleMode] = mapped_column(_enum(RuleMode))
    person_id: Mapped[int | None] = mapped_column(ForeignKey("core.person.id"))
    rotation_period: Mapped[RotationPeriod | None] = mapped_column(_enum(RotationPeriod))
    anchor_date: Mapped[date | None] = mapped_column(Date)

    duty: Mapped[Duty] = relationship(back_populates="rules")
    rotation: Mapped[list["RotationMember"]] = relationship(
        cascade="all, delete-orphan", order_by="RotationMember.position", lazy="selectin"
    )


class RotationMember(Base):
    """One person in a rotation, in order."""

    __tablename__ = "rule_rotation"
    __table_args__ = {"schema": SCHEMA}

    rule_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.rule.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("core.person.id"))


class Swap(Base):
    """A one-off assignee for a duty on one date."""

    __tablename__ = "swap"
    __table_args__ = (UniqueConstraint("duty_id", "date"), {"schema": SCHEMA})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    duty_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.duty.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column("date", Date)
    person_id: Mapped[int] = mapped_column(ForeignKey("core.person.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
