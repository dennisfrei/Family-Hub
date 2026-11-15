"""Blood pressure readings.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "blood_pressure"')
    op.create_table(
        "reading",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("systolic", sa.Integer(), nullable=False),
        sa.Column("diastolic", sa.Integer(), nullable=False),
        sa.Column("pulse", sa.Integer(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["core.person.id"], name=op.f("fk_reading_person_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reading")),
        schema="blood_pressure",
    )
    op.create_index(
        op.f("ix_blood_pressure_reading_person_id"), "reading", ["person_id"], unique=False, schema="blood_pressure"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_blood_pressure_reading_person_id"), table_name="reading", schema="blood_pressure")
    op.drop_table("reading", schema="blood_pressure")
    op.execute('DROP SCHEMA IF EXISTS "blood_pressure"')
