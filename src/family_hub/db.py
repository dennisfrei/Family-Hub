"""Database engine, session factory and declarative base."""

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all module models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str, **engine_kwargs) -> AsyncEngine:
    """Create the engine and session factory.

    Args:
        url: SQLAlchemy async database URL.
        **engine_kwargs: Passed to `create_async_engine`.

    Returns:
        The created engine.
    """
    global _engine, _sessionmaker
    _engine = create_async_engine(url, **engine_kwargs)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session() -> AsyncSession:
    """Open a new session; use it as an async context manager.

    Raises:
        RuntimeError: If `init_engine` was not called.
    """
    if _sessionmaker is None:
        raise RuntimeError("Database engine is not initialised")
    return _sessionmaker()


async def provide_session() -> AsyncIterator[AsyncSession]:
    """Yield a session for Litestar dependency injection."""
    async with session() as db_session:
        yield db_session


async def dispose_engine() -> None:
    """Close all pooled connections."""
    if _engine is not None:
        await _engine.dispose()
