"""Liveness and readiness probes under `/api`, reachable without a token."""

import asyncio
import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from litestar import Response, get
from litestar.status_codes import HTTP_503_SERVICE_UNAVAILABLE
from litestar.types import ControllerRouterHandler
from sqlalchemy import text

from family_hub import db

logger = logging.getLogger(__name__)

READY_TIMEOUT_SECONDS = 2.0


def expected_revision(alembic_ini: Path) -> str | None:
    """Latest migration shipped with the app; None if the migrations are not available."""
    if not alembic_ini.is_file():
        return None
    return ScriptDirectory.from_config(Config(str(alembic_ini))).get_current_head()


async def current_revision() -> str | None:
    """Migration the database is at."""
    async with db.session() as session:
        return await session.scalar(text("SELECT version_num FROM alembic_version"))


def create_handlers(alembic_ini: Path) -> list[ControllerRouterHandler]:
    """Build the probe handlers; the expected schema revision is read once."""
    expected = expected_revision(alembic_ini)

    @get("/healthz", tags=["health"], exclude_from_auth=True)
    async def healthz() -> dict[str, str]:
        """Liveness: the process answers."""
        return {"status": "ok"}

    @get("/readyz", tags=["health"], exclude_from_auth=True)
    async def readyz() -> Response[dict[str, str | None]]:
        """Readiness: database reachable and schema at the latest migration."""
        try:
            async with asyncio.timeout(READY_TIMEOUT_SECONDS):
                revision = await current_revision()
        except Exception as exc:
            logger.warning(f"Readiness check failed: {exc!r}")
            return Response(
                {"status": "unavailable", "database": "unreachable"}, status_code=HTTP_503_SERVICE_UNAVAILABLE
            )
        if expected is not None and revision != expected:
            body = {"status": "unavailable", "schema": revision, "expected": expected}
            return Response(body, status_code=HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok", "database": "ok", "schema": revision})

    return [healthz, readyz]
