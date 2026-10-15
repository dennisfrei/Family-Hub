"""Fever endpoints for external clients under `/api/fever`."""

from litestar import Controller, delete, get, post
from litestar.di import NamedDependency
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import FromPath, FromQuery
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core.service import PersonNotFoundError
from family_hub.fever import service
from family_hub.fever.schemas import EpisodeDetail, EpisodeRead, QuickReadingWrite, ReadingRead


class FeverController(Controller):
    """Episodes and readings."""

    path = "/fever"
    tags = ["fever"]

    @get("/episodes")
    async def list_episodes(
        self,
        session: NamedDependency[AsyncSession],
        person_id: FromQuery[int | None] = None,
        open_only: FromQuery[bool] = False,
    ) -> list[EpisodeRead]:
        """List episodes, newest first."""
        return await service.list_episodes(session, person_id=person_id, open_only=open_only)

    @get("/episodes/{episode_id:int}")
    async def get_episode(self, session: NamedDependency[AsyncSession], episode_id: FromPath[int]) -> EpisodeDetail:
        """Return an episode with its readings."""
        try:
            return await service.get_episode(session, episode_id)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc

    @post("/readings")
    async def add_reading(self, session: NamedDependency[AsyncSession], data: QuickReadingWrite) -> ReadingRead:
        """Add a reading to the person's open episode (started automatically if needed)."""
        try:
            return await service.quick_add_reading(session, data)
        except PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    @delete("/readings/{reading_id:int}")
    async def delete_reading(self, session: NamedDependency[AsyncSession], reading_id: FromPath[int]) -> None:
        """Delete a reading."""
        try:
            await service.delete_reading(session, reading_id)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc

    @get("/export")
    async def export(self, session: NamedDependency[AsyncSession]) -> list[EpisodeDetail]:
        """Export all episodes with readings."""
        return await service.export_all(session)
