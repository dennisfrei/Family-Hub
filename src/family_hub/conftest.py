"""Shared fixtures. Tests using the database are integration tests against PostgreSQL, marked automatically."""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from litestar.testing import AsyncTestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from family_hub import db
from family_hub.app import MODULES, create_api
from family_hub.auth import create_token
from family_hub.config import Settings, get_settings
from family_hub.main import run_migrations


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return Settings(_env_file=None, database_url=explicit).database_url
    url = make_url(Settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()
API_SETTINGS = Settings(_env_file=None, jwt_secret=SecretStr("x" * 32))
DATABASE_FIXTURES = {"database", "session", "app_user", "new_install_user"}
FAKE_SESSION = MagicMock(spec=AsyncSession)


@pytest.fixture(autouse=True)
def _ignore_env_file(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never read the developer's `.env`; only the test database URL is derived from it."""
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test that needs PostgreSQL as `integration`."""
    for item in items:
        if DATABASE_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.integration)


async def _create_database(url: str) -> None:
    target = make_url(url)
    engine = create_async_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        await engine.dispose()


async def reset_database(engine: AsyncEngine) -> None:
    """Empty all tables and restart their ids."""
    tables = ", ".join(f'"{table.schema}"."{table.name}"' for table in db.Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def database() -> str:
    """URL of the test database, created if needed and migrated to the latest revision."""
    try:
        asyncio.run(_create_database(TEST_DATABASE_URL))
    except (OperationalError, OSError) as exc:
        pytest.exit(f"PostgreSQL for integration tests not reachable ({exc}); start it with `make db`", returncode=1)
    run_migrations(Settings(_env_file=None, database_url=TEST_DATABASE_URL))
    return TEST_DATABASE_URL


@pytest.fixture
async def session(database: str) -> AsyncIterator[AsyncSession]:
    """A session on the emptied test database."""
    engine = db.init_engine(database, poolclass=NullPool)
    await reset_database(engine)
    async with db.session() as db_session:
        yield db_session
    await db.dispose_engine()


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Callable[[], AsyncTestClient]:
    """Factory for API clients with a valid token and no database; tests patch the service functions."""

    async def fake_session() -> AsyncIterator[AsyncSession]:
        yield FAKE_SESSION

    async def accept(token_id: str) -> bool:
        return True

    monkeypatch.setattr(db, "provide_session", fake_session)

    def build() -> AsyncTestClient:
        token, _ = create_token(API_SETTINGS, "test", timedelta(minutes=5))
        client = AsyncTestClient(app=create_api(MODULES, API_SETTINGS, token_check=accept))
        client.headers["Authorization"] = f"Bearer {token}"
        return client

    return build
