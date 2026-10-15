"""Read-only core endpoints for external clients under `/api/core`."""

from litestar import Controller, get
from litestar.di import NamedDependency
from litestar.exceptions import NotFoundException
from litestar.params import FromPath, FromQuery
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service
from family_hub.core.schemas import ChildRead, PersonRead


class CoreController(Controller):
    """People and children."""

    path = "/core"
    tags = ["core"]

    @get("/children")
    async def list_children(self, session: NamedDependency[AsyncSession]) -> list[ChildRead]:
        """List active children with their current age."""
        return await service.list_children(session)

    @get("/people")
    async def list_people(
        self, session: NamedDependency[AsyncSession], include_inactive: FromQuery[bool] = False
    ) -> list[PersonRead]:
        """List people."""
        return await service.list_people(session, include_inactive=include_inactive)

    @get("/people/{person_id:int}")
    async def get_person(self, session: NamedDependency[AsyncSession], person_id: FromPath[int]) -> PersonRead:
        """Return one person."""
        try:
            return await service.get_person(session, person_id)
        except service.PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
