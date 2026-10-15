"""Admin logic: API tokens, deleting people for good, system facts."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub import app_version, db
from family_hub.admin.schemas import ApiTokenRead, IssuedToken, ModuleUsage, SystemInfo, TableCount
from family_hub.auth import create_token
from family_hub.backup import dump
from family_hub.config import Settings
from family_hub.core import service as core_service
from family_hub.core.models import ApiToken
from family_hub.errors import InvalidInputError
from family_hub.module import Module

logger = logging.getLogger(__name__)

MAX_TOKEN_DAYS = 3650
LAST_USED_RESOLUTION = timedelta(minutes=5)


class TokenNotFoundError(LookupError):
    """Raised when a token id does not exist."""


def _token_read(token: ApiToken) -> ApiTokenRead:
    return ApiTokenRead(
        id=token.id,
        token_id=token.token_id,
        name=token.name,
        created_at=token.created_at,
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        last_used_at=token.last_used_at,
    )


async def issue_token(session: AsyncSession, settings: Settings, name: str, days: int) -> IssuedToken:
    """Create and register a token for an API client.

    Raises:
        InvalidInputError: If the name is empty or the validity out of range.
    """
    name = name.strip()
    if not name:
        raise InvalidInputError("error.name_required")
    if not 1 <= days <= MAX_TOKEN_DAYS:
        raise InvalidInputError("error.token_days", max=MAX_TOKEN_DAYS)
    valid_for = timedelta(days=days)
    token, token_id = create_token(settings, name, valid_for)
    row = ApiToken(token_id=token_id, name=name, expires_at=datetime.now(UTC) + valid_for)
    session.add(row)
    await session.commit()
    logger.info(f"Issued API token {row.id} for {name}")
    return IssuedToken(token=token, info=_token_read(row))


async def list_tokens(session: AsyncSession) -> list[ApiTokenRead]:
    """All tokens, newest first."""
    result = await session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc()))
    return [_token_read(token) for token in result]


async def revoke_token(session: AsyncSession, token_pk: int) -> ApiTokenRead:
    """Revoke a token; revoking twice keeps the first date.

    Raises:
        TokenNotFoundError: If the id does not exist.
    """
    token = await session.get(ApiToken, token_pk)
    if token is None:
        raise TokenNotFoundError(f"Token {token_pk} not found")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await session.commit()
        logger.info(f"Revoked API token {token_pk}")
    return _token_read(token)


async def use_token(session: AsyncSession, token_id: str) -> bool:
    """Whether a token id is registered and not revoked; records the use."""
    token = await session.scalar(select(ApiToken).where(ApiToken.token_id == token_id))
    if token is None or token.revoked_at is not None:
        return False
    now = datetime.now(UTC)
    last_used = token.last_used_at
    if last_used is None or now - last_used > LAST_USED_RESOLUTION:
        token.last_used_at = now
        await session.commit()
    return True


async def token_is_valid(token_id: str) -> bool:
    """`use_token` with its own session, for the JWT revocation check."""
    async with db.session() as session:
        return await use_token(session, token_id)


async def person_usage(session: AsyncSession, person_id: int, modules: list[Module]) -> list[ModuleUsage]:
    """What each module keeps about a person; modules without data are left out.

    Raises:
        PersonNotFoundError: If the id does not exist.
    """
    await core_service.get_person(session, person_id)
    usage = []
    for module in modules:
        if module.person_data is None:
            continue
        items = {key: count for key, count in (await module.person_data.count(session, person_id)).items() if count}
        if items:
            usage.append(ModuleUsage(module=module.name, label_key=module.label_key, items=items))
    return usage


async def delete_person(session: AsyncSession, person_id: int, modules: list[Module]) -> None:
    """Delete a person with all module data in one transaction.

    Raises:
        PersonNotFoundError: If the id does not exist.
    """
    await core_service.get_person(session, person_id)
    for module in modules:
        if module.person_data is not None:
            await module.person_data.delete(session, person_id)
    await core_service.delete_person(session, person_id)
    await session.commit()
    session.expire_all()
    logger.info(f"Deleted person {person_id} with all data")


async def system_info(session: AsyncSession, settings: Settings) -> SystemInfo:
    """Version, database and data volume."""
    connection = await session.connection()
    tables: list[TableCount] = []
    for table in db.Base.metadata.sorted_tables:
        rows = await session.scalar(select(func.count()).select_from(table)) or 0
        tables.append(TableCount(name=f"{table.schema}.{table.name}", rows=rows))
    tables.sort(key=lambda table: table.name)
    server = connection.dialect.server_version_info
    database = connection.dialect.name + (f" {'.'.join(str(part) for part in server)}" if server else "")
    reference_dir = settings.growth_reference_dir
    reference_files = len(list(reference_dir.glob("*.csv"))) if reference_dir and reference_dir.is_dir() else 0
    bucket = settings.backup_bucket
    return SystemInfo(
        version=app_version(),
        schema_revision=await dump.schema_revision(connection),
        database=database,
        timezone=settings.timezone,
        reference_files=reference_files,
        backup_target=f"s3://{bucket}/{settings.backup_prefix}" if bucket else None,
        tables=tables,
    )
