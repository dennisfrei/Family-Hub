"""Blood pressure endpoints for external clients under `/api/blood-pressure`."""

from litestar import Controller, delete, get, post
from litestar.di import NamedDependency
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import FromPath, FromQuery
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.blood_pressure import service
from family_hub.blood_pressure.schemas import ReadingRead, ReadingWrite
from family_hub.core.service import PersonNotFoundError


class BloodPressureController(Controller):
    """Blood pressure readings."""

    path = "/blood-pressure"
    tags = ["blood-pressure"]

    @get("/readings")
    async def list_readings(
        self,
        session: NamedDependency[AsyncSession],
        person_id: FromQuery[int | None] = None,
        limit: FromQuery[int | None] = None,
        offset: FromQuery[int] = 0,
    ) -> list[ReadingRead]:
        """List readings, newest first; `limit` and `offset` page through them."""
        return await service.list_readings(session, person_id=person_id, limit=limit, offset=offset)

    @post("/readings")
    async def add_reading(self, session: NamedDependency[AsyncSession], data: ReadingWrite) -> ReadingRead:
        """Add a reading for a person."""
        try:
            return await service.add_reading(session, data)
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
