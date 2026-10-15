"""Rhythm (duties, rules, swaps) and time capsule (entries, tags), with preset duties.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALL_DAYS = 0b1111111
WORKDAYS = 0b0011111
PRESET_DUTIES = [
    ("Morgens", "wb_sunny", "#d97706", "morning", ALL_DAYS),
    ("Kita bringen", "directions_walk", "#1f6f63", "morning", WORKDAYS),
    ("Kita abholen", "child_care", "#2563eb", "afternoon", WORKDAYS),
    ("Zubettbringen", "bedtime", "#475569", "evening", ALL_DAYS),
]


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "rhythm"')
    op.execute('CREATE SCHEMA IF NOT EXISTS "time_capsule"')
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tag")),
        sa.UniqueConstraint("name", name=op.f("uq_tag_name")),
        schema="time_capsule",
    )
    op.create_table(
        "duty",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column(
            "time_of_day",
            sa.Enum("morning", "afternoon", "evening", name="timeofday", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("weekdays", sa.Integer(), nullable=False),
        sa.Column("is_preset", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("for_person_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["for_person_id"], ["core.person.id"], name=op.f("fk_duty_for_person_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_duty")),
        schema="rhythm",
    )
    op.create_table(
        "entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context", sa.String(length=500), nullable=True),
        sa.Column(
            "type",
            sa.Enum("saying", "moment", "milestone", name="entrytype", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["core.person.id"], name=op.f("fk_entry_author_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entry")),
        schema="time_capsule",
    )
    op.create_index(op.f("ix_time_capsule_entry_date"), "entry", ["date"], unique=False, schema="time_capsule")
    op.create_table(
        "rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("duty_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("mode", sa.Enum("fixed", "rotation", name="rulemode", native_enum=False, length=16), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column(
            "rotation_period",
            sa.Enum("daily", "weekly", name="rotationperiod", native_enum=False, length=16),
            nullable=True,
        ),
        sa.Column("anchor_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["duty_id"], ["rhythm.duty.id"], name=op.f("fk_rule_duty_id_duty"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["core.person.id"], name=op.f("fk_rule_person_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule")),
        sa.UniqueConstraint("duty_id", "weekday", name=op.f("uq_rule_duty_id")),
        schema="rhythm",
    )
    op.create_index(op.f("ix_rhythm_rule_duty_id"), "rule", ["duty_id"], unique=False, schema="rhythm")
    op.create_table(
        "swap",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("duty_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["duty_id"], ["rhythm.duty.id"], name=op.f("fk_swap_duty_id_duty"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["core.person.id"], name=op.f("fk_swap_person_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_swap")),
        sa.UniqueConstraint("duty_id", "date", name=op.f("uq_swap_duty_id")),
        schema="rhythm",
    )
    op.create_index(op.f("ix_rhythm_swap_duty_id"), "swap", ["duty_id"], unique=False, schema="rhythm")
    op.create_table(
        "entry_person",
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["time_capsule.entry.id"], name=op.f("fk_entry_person_entry_id_entry"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["person_id"], ["core.person.id"], name=op.f("fk_entry_person_person_id_person")),
        sa.PrimaryKeyConstraint("entry_id", "person_id", name=op.f("pk_entry_person")),
        schema="time_capsule",
    )
    op.create_index(
        op.f("ix_time_capsule_entry_person_person_id"),
        "entry_person",
        ["person_id"],
        unique=False,
        schema="time_capsule",
    )
    op.create_table(
        "entry_tag",
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["time_capsule.entry.id"], name=op.f("fk_entry_tag_entry_id_entry"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["time_capsule.tag.id"], name=op.f("fk_entry_tag_tag_id_tag"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("entry_id", "tag_id", name=op.f("pk_entry_tag")),
        schema="time_capsule",
    )
    op.create_table(
        "rule_rotation",
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["core.person.id"], name=op.f("fk_rule_rotation_person_id_person")),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["rhythm.rule.id"], name=op.f("fk_rule_rotation_rule_id_rule"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("rule_id", "position", name=op.f("pk_rule_rotation")),
        schema="rhythm",
    )
    duty = sa.table(
        "duty",
        sa.column("name", sa.String),
        sa.column("icon", sa.String),
        sa.column("color", sa.String),
        sa.column("time_of_day", sa.String),
        sa.column("weekdays", sa.Integer),
        sa.column("is_preset", sa.Boolean),
        sa.column("active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        schema="rhythm",
    )
    op.bulk_insert(
        duty,
        [
            {
                "name": name,
                "icon": icon,
                "color": color,
                "time_of_day": time,
                "weekdays": days,
                "is_preset": True,
                "active": True,
                "sort_order": order,
            }
            for order, (name, icon, color, time, days) in enumerate(PRESET_DUTIES)
        ],
    )


def downgrade() -> None:
    op.drop_table("rule_rotation", schema="rhythm")
    op.drop_table("entry_tag", schema="time_capsule")
    op.drop_index(op.f("ix_time_capsule_entry_person_person_id"), table_name="entry_person", schema="time_capsule")
    op.drop_table("entry_person", schema="time_capsule")
    op.drop_index(op.f("ix_rhythm_swap_duty_id"), table_name="swap", schema="rhythm")
    op.drop_table("swap", schema="rhythm")
    op.drop_index(op.f("ix_rhythm_rule_duty_id"), table_name="rule", schema="rhythm")
    op.drop_table("rule", schema="rhythm")
    op.drop_index(op.f("ix_time_capsule_entry_date"), table_name="entry", schema="time_capsule")
    op.drop_table("entry", schema="time_capsule")
    op.drop_table("duty", schema="rhythm")
    op.drop_table("tag", schema="time_capsule")
    op.execute('DROP SCHEMA IF EXISTS "time_capsule"')
    op.execute('DROP SCHEMA IF EXISTS "rhythm"')
