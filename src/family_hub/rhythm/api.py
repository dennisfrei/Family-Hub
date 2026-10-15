"""Rhythm endpoints for external clients under `/api/rhythm`."""

from datetime import date
from typing import Annotated

from litestar import Controller, delete, get, post, put
from litestar.di import NamedDependency
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import FromPath, FromQuery, QueryParameter
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core.service import PersonNotFoundError
from family_hub.rhythm import service
from family_hub.rhythm.schemas import DutyRead, DutyStat, DutyWrite, RuleWrite, SwapWrite, WeekRead


class RhythmController(Controller):
    """Weekly schedule, duties, rules and swaps."""

    path = "/rhythm"
    tags = ["rhythm"]

    @get("/week")
    async def week(self, session: NamedDependency[AsyncSession], start: FromQuery[date | None] = None) -> WeekRead:
        """Resolved schedule of the week containing `start` (default: today)."""
        return await service.week(session, start or date.today())

    @get("/stats")
    async def stats(
        self,
        session: NamedDependency[AsyncSession],
        first: Annotated[date, QueryParameter(name="from")],
        last: Annotated[date | None, QueryParameter(name="to")] = None,
    ) -> list[DutyStat]:
        """Planned assignments per duty and person in a period (default: until today)."""
        return await service.duty_stats(session, first, last or date.today())

    @get("/duties")
    async def list_duties(
        self, session: NamedDependency[AsyncSession], include_inactive: FromQuery[bool] = False
    ) -> list[DutyRead]:
        """List duties with their rules."""
        return await service.list_duties(session, include_inactive=include_inactive)

    @post("/duties")
    async def create_duty(self, session: NamedDependency[AsyncSession], data: DutyWrite) -> DutyRead:
        """Create a duty."""
        try:
            return await service.create_duty(session, data)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    @put("/duties/{duty_id:int}")
    async def update_duty(
        self, session: NamedDependency[AsyncSession], duty_id: FromPath[int], data: DutyWrite
    ) -> DutyRead:
        """Replace a duty."""
        try:
            return await service.update_duty(session, duty_id, data)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    @delete("/duties/{duty_id:int}")
    async def delete_duty(self, session: NamedDependency[AsyncSession], duty_id: FromPath[int]) -> None:
        """Delete a duty."""
        try:
            await service.delete_duty(session, duty_id)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc

    @get("/duties/{duty_id:int}/rules")
    async def get_rules(self, session: NamedDependency[AsyncSession], duty_id: FromPath[int]) -> DutyRead:
        """Return a duty with its rules."""
        try:
            return await service.get_duty(session, duty_id)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc

    @put("/duties/{duty_id:int}/rules")
    async def set_rules(
        self, session: NamedDependency[AsyncSession], duty_id: FromPath[int], data: list[RuleWrite]
    ) -> DutyRead:
        """Replace the rules of a duty."""
        try:
            return await service.set_rules(session, duty_id, data)
        except (service.NotFoundError, PersonNotFoundError) as exc:
            raise NotFoundException(str(exc)) from exc
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    @post("/swaps")
    async def create_swap(self, session: NamedDependency[AsyncSession], data: SwapWrite) -> None:
        """Assign a person to a duty for one date."""
        try:
            await service.set_swap(session, data.duty_id, data.date, data.person_id)
        except (service.NotFoundError, PersonNotFoundError) as exc:
            raise NotFoundException(str(exc)) from exc
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    @delete("/swaps")
    async def delete_swap(
        self,
        session: NamedDependency[AsyncSession],
        duty_id: FromQuery[int],
        day: Annotated[date, QueryParameter(name="date")],
    ) -> None:
        """Undo a swap."""
        await service.remove_swap(session, duty_id, day)
