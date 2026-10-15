"""Core people and child profiles.

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "core"')
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.Enum("adult", "child", name="personkind", native_enum=False, length=16), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_person"),
        schema="core",
    )
    op.create_table(
        "child_profile",
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("sex", sa.Enum("female", "male", name="sex", native_enum=False, length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id"], ["core.person.id"], name="fk_child_profile_person_id_person", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("person_id", name="pk_child_profile"),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("child_profile", schema="core")
    op.drop_table("person", schema="core")
    op.execute('DROP SCHEMA IF EXISTS "core"')
