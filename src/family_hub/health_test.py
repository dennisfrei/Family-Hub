from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub import health
from family_hub.app import MODULES, create_api
from family_hub.conftest import API_SETTINGS

HEAD = health.expected_revision(Path("alembic.ini"))


@pytest.mark.parametrize(
    ("revision", "status"),
    [(AsyncMock(return_value=HEAD), 200), (AsyncMock(return_value="0001"), 503), (AsyncMock(side_effect=OSError), 503)],
)
async def test_readyz(monkeypatch: pytest.MonkeyPatch, revision: AsyncMock, status: int) -> None:
    monkeypatch.setattr(health, "current_revision", revision)

    async with AsyncTestClient(app=create_api(MODULES, API_SETTINGS)) as client:
        response = await client.get("/readyz")

    assert response.status_code == status


def test_expected_revision_without_migrations(tmp_path: Path) -> None:
    assert health.expected_revision(tmp_path / "alembic.ini") is None


async def test_ready_against_migrated_database(session: AsyncSession) -> None:
    async with AsyncTestClient(app=create_api(MODULES, API_SETTINGS)) as client:
        response = await client.get("/readyz")

    assert response.json() == {"status": "ok", "database": "ok", "schema": HEAD}
