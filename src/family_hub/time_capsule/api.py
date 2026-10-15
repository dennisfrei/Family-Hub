"""Time capsule endpoints under `/api/time-capsule` (also used by the iOS Shortcut)."""

from datetime import date
from enum import StrEnum
from typing import Annotated

from litestar import Controller, Response, delete, get, post, put
from litestar.di import NamedDependency
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import FromPath, FromQuery, QueryParameter
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.time_capsule import export, service
from family_hub.time_capsule.models import EntryType
from family_hub.time_capsule.schemas import EntryFilter, EntryRead, EntryWrite, TagRead


class ExportFormat(StrEnum):
    """Supported export formats."""

    JSON = "json"
    MARKDOWN = "md"
    PDF = "pdf"


class TimeCapsuleController(Controller):
    """Entries, tags, on-this-day and exports."""

    path = "/time-capsule"
    tags = ["time-capsule"]

    @get("/entries")
    async def list_entries(
        self,
        session: NamedDependency[AsyncSession],
        child: FromQuery[int | None] = None,
        entry_type: Annotated[EntryType | None, QueryParameter(name="type")] = None,
        tag: FromQuery[str | None] = None,
        year: FromQuery[int | None] = None,
        q: FromQuery[str | None] = None,
    ) -> list[EntryRead]:
        """List and filter entries, newest first."""
        filters = EntryFilter(person_id=child, type=entry_type, tag=tag, year=year, query=q)
        return await service.list_entries(session, filters)

    @post("/entries")
    async def create_entry(self, session: NamedDependency[AsyncSession], data: EntryWrite) -> EntryRead:
        """Create an entry (quick capture)."""
        try:
            return await service.create_entry(session, data)
        except core_service.PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    @get("/entries/{entry_id:int}")
    async def get_entry(self, session: NamedDependency[AsyncSession], entry_id: FromPath[int]) -> EntryRead:
        """Return one entry."""
        try:
            return await service.get_entry(session, entry_id)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc

    @put("/entries/{entry_id:int}")
    async def update_entry(
        self, session: NamedDependency[AsyncSession], entry_id: FromPath[int], data: EntryWrite
    ) -> EntryRead:
        """Replace an entry."""
        try:
            return await service.update_entry(session, entry_id, data)
        except (service.NotFoundError, core_service.PersonNotFoundError) as exc:
            raise NotFoundException(str(exc)) from exc
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    @delete("/entries/{entry_id:int}")
    async def delete_entry(self, session: NamedDependency[AsyncSession], entry_id: FromPath[int]) -> None:
        """Delete an entry."""
        try:
            await service.delete_entry(session, entry_id)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc

    @get("/on-this-day")
    async def on_this_day(
        self,
        session: NamedDependency[AsyncSession],
        day: Annotated[date | None, QueryParameter(name="date")] = None,
    ) -> list[EntryRead]:
        """Entries from the same day in earlier years (default: today)."""
        return await service.on_this_day(session, day or date.today())

    @get("/tags")
    async def list_tags(self, session: NamedDependency[AsyncSession]) -> list[TagRead]:
        """Tags with counts."""
        return await service.list_tags(session)

    @get("/export")
    async def export(
        self,
        session: NamedDependency[AsyncSession],
        export_format: Annotated[ExportFormat, QueryParameter(name="format")] = ExportFormat.JSON,
        child: FromQuery[int | None] = None,
        year: FromQuery[int | None] = None,
    ) -> Response[bytes]:
        """Export as JSON or Markdown, or a PDF booklet (needs `child` and `year`)."""
        entries = await service.list_entries(session, EntryFilter(person_id=child, year=year))
        if export_format is ExportFormat.JSON:
            return Response(export.to_json(entries).encode(), media_type="application/json")
        if export_format is ExportFormat.MARKDOWN:
            return Response(export.to_markdown(entries, "Zeitkapsel").encode(), media_type="text/markdown")
        if child is None or year is None:
            raise ValidationException("The PDF booklet needs child and year")
        try:
            person = await core_service.get_person(session, child)
        except core_service.PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        return Response(
            export.booklet_pdf(entries, person.name, year),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="zeitkapsel-{year}.pdf"'},
        )
