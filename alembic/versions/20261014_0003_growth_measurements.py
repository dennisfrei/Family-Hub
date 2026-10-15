"""Growth measurements.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "growth"')
    op.create_table(
        "measurement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum("weight", "length", "head", name="measurementtype", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("official", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("import_ref", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["core.person.id"], name=op.f("fk_measurement_person_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_measurement")),
        sa.UniqueConstraint("import_ref", name=op.f("uq_measurement_import_ref")),
        schema="growth",
    )
    op.create_index(
        op.f("ix_growth_measurement_person_id"), "measurement", ["person_id"], unique=False, schema="growth"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_growth_measurement_person_id"), table_name="measurement", schema="growth")
    op.drop_table("measurement", schema="growth")
    op.execute('DROP SCHEMA IF EXISTS "growth"')
