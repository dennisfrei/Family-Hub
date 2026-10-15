"""Export and import all tables as JSON-compatible data, independent of `pg_dump`."""

import hashlib
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Integer, Table, delete, func, insert, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from family_hub.models import metadata

logger = logging.getLogger(__name__)

BACKUP_FORMAT_VERSION = "1.0"

# Backup payloads are arbitrary JSON documents
type BackupData = dict[str, Any]


def _tables() -> list[Table]:
    return list(metadata.sorted_tables)


def _key(table: Table) -> str:
    return f"{table.schema}.{table.name}" if table.schema else table.name


def json_default(value: object) -> str | float:
    """Serialize dates and decimals for `json.dumps`."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def content_hash(data: BackupData) -> str:
    """Hash of the data without the export timestamp, to detect unchanged backups."""
    content = {key: data[key] for key in ("version", "schema_revision", "tables")}
    payload = json.dumps(content, default=json_default, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def schema_revision(connection: AsyncConnection) -> str | None:
    """Return the current Alembic revision, or None if the database is not migrated."""
    try:
        async with connection.begin_nested():
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        return None


async def export_data(connection: AsyncConnection) -> BackupData:
    """Read every table, ordered by primary key."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in _tables():
        result = await connection.execute(select(table).order_by(*table.primary_key.columns))
        tables[_key(table)] = [dict(row._mapping) for row in result]
    logger.info("Exported " + ", ".join(f"{len(rows)} {name}" for name, rows in tables.items()))
    return {
        "version": BACKUP_FORMAT_VERSION,
        "schema_revision": await schema_revision(connection),
        "exported_at": datetime.now().isoformat(),
        "tables": tables,
    }


def _parse_row(table: Table, item: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for column in table.columns:
        if column.key not in item:
            continue
        value = item[column.key]
        if isinstance(value, str) and isinstance(column.type, DateTime):
            value = datetime.fromisoformat(value)
        elif isinstance(value, str) and isinstance(column.type, Date):
            value = date.fromisoformat(value)
        values[column.key] = value
    return values


async def _reset_sequences(connection: AsyncConnection, table: Table) -> None:
    for column in table.primary_key.columns:
        if not isinstance(column.type, Integer) or column.foreign_keys:
            continue
        name = _key(table)
        max_id = await connection.scalar(select(func.max(column)))
        await connection.execute(
            text("SELECT setval(pg_get_serial_sequence(:table, :column), :value, :called)"),
            {"table": name, "column": column.name, "value": max_id or 1, "called": max_id is not None},
        )


async def import_data(connection: AsyncConnection, data: BackupData) -> None:
    """Replace all data with the backup content; run inside one transaction.

    Raises:
        RuntimeError: If the database is not migrated or the backup is malformed.
    """
    if not isinstance(data.get("tables"), dict):
        raise RuntimeError("Invalid backup format: missing 'tables'")
    current = await schema_revision(connection)
    if current is None:
        raise RuntimeError("Database schema missing; run the migrations first")
    backup_revision = data.get("schema_revision")
    if backup_revision and backup_revision != current:
        logger.warning(f"Backup is from schema revision {backup_revision}, database is at {current}")

    tables = _tables()
    for table in reversed(tables):
        await connection.execute(delete(table))
    for table in tables:
        rows = [_parse_row(table, item) for item in data["tables"].get(_key(table), [])]
        if rows:
            await connection.execute(insert(table), rows)
        if connection.dialect.name == "postgresql":
            await _reset_sequences(connection, table)
        logger.info(f"Imported {len(rows)} {_key(table)}")
