"""Alembic environment: async migrations for all module schemas."""

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.runtime.environment import NameFilterParentNames, NameFilterType
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from family_hub.config import get_settings
from family_hub.models import SCHEMAS, metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _include_name(name: str | None, type_: NameFilterType, parent_names: NameFilterParentNames) -> bool:
    if type_ == "schema":
        return name in SCHEMAS
    return True


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=_include_name,
        literal_binds=connection is None,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection."""
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    for schema in sorted(SCHEMAS):
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    engine = create_async_engine(_database_url())
    async with engine.begin() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
