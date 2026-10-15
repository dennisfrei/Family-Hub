"""Fever episodes and readings.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "fever"')
    op.create_table(
        "episode",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_ref", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["core.person.id"], name=op.f("fk_episode_person_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_episode")),
        sa.UniqueConstraint("import_ref", name=op.f("uq_episode_import_ref")),
        schema="fever",
    )
    op.create_index(op.f("ix_fever_episode_person_id"), "episode", ["person_id"], unique=False, schema="fever")
    op.create_table(
        "reading",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "method",
            sa.Enum("ear", "rectal", "forehead", "armpit", "oral", name="method", native_enum=False, length=16),
            nullable=True,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"], ["fever.episode.id"], name=op.f("fk_reading_episode_id_episode"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reading")),
        schema="fever",
    )
    op.create_index(op.f("ix_fever_reading_episode_id"), "reading", ["episode_id"], unique=False, schema="fever")


def downgrade() -> None:
    op.drop_index(op.f("ix_fever_reading_episode_id"), table_name="reading", schema="fever")
    op.drop_table("reading", schema="fever")
    op.drop_index(op.f("ix_fever_episode_person_id"), table_name="episode", schema="fever")
    op.drop_table("episode", schema="fever")
    op.execute('DROP SCHEMA IF EXISTS "fever"')
