"""Growth endpoints for external clients under `/api/growth`."""

from enum import StrEnum
from typing import Annotated

from litestar import Controller, Response, delete, get, post
from litestar.di import NamedDependency
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import FromPath, FromQuery, QueryParameter
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core.service import PersonNotFoundError
from family_hub.growth import report, service
from family_hub.growth.models import MeasurementType
from family_hub.growth.schemas import MeasurementRead, MeasurementWrite, TypeStatus


class ReportFormat(StrEnum):
    """Report file formats."""

    PDF = "pdf"
    HTML = "html"
    CSV = "csv"


REPORT_BUILDERS = {
    ReportFormat.PDF: (report.build_pdf, "application/pdf"),
    ReportFormat.HTML: (report.build_html, "text/html"),
    ReportFormat.CSV: (report.build_csv, "text/csv"),
}


class GrowthController(Controller):
    """Measurements with percentiles."""

    path = "/growth"
    tags = ["growth"]

    @get("/measurements")
    async def list_measurements(
        self,
        session: NamedDependency[AsyncSession],
        person_id: FromQuery[int],
        measurement_type: Annotated[MeasurementType | None, QueryParameter(name="type")] = None,
    ) -> list[MeasurementRead]:
        """List a child's measurements, oldest first."""
        try:
            return await service.list_measurements(session, person_id, measurement_type)
        except PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        except service.NotAChildError as exc:
            raise ValidationException(str(exc)) from exc

    @post("/measurements")
    async def add_measurement(self, session: NamedDependency[AsyncSession], data: MeasurementWrite) -> MeasurementRead:
        """Add a measurement."""
        try:
            [created] = await service.add_measurements(session, [data])
        except PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc
        return created

    @delete("/measurements/{measurement_id:int}")
    async def delete_measurement(self, session: NamedDependency[AsyncSession], measurement_id: FromPath[int]) -> None:
        """Delete a measurement."""
        try:
            await service.delete_measurement(session, measurement_id)
        except service.NotFoundError as exc:
            raise NotFoundException(str(exc)) from exc

    @get("/status")
    async def status(self, session: NamedDependency[AsyncSession], person_id: FromQuery[int]) -> list[TypeStatus]:
        """Latest and previous measurement per type."""
        try:
            return await service.status(session, person_id)
        except PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        except service.NotAChildError as exc:
            raise ValidationException(str(exc)) from exc

    @get("/report")
    async def growth_report(
        self,
        session: NamedDependency[AsyncSession],
        person_id: FromQuery[int],
        report_format: Annotated[ReportFormat, QueryParameter(name="format")] = ReportFormat.PDF,
    ) -> Response[bytes]:
        """Growth report of a child as PDF, HTML or CSV, as in the earlier growth app."""
        try:
            data = await report.load(session, person_id)
        except PersonNotFoundError as exc:
            raise NotFoundException(str(exc)) from exc
        except service.NotAChildError as exc:
            raise ValidationException(str(exc)) from exc
        build, media_type = REPORT_BUILDERS[report_format]
        return Response(
            build(data),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{data.file_stem()}.{report_format.value}"'},
        )

    @get("/export")
    async def export(self, session: NamedDependency[AsyncSession]) -> list[MeasurementRead]:
        """Export all measurements."""
        return await service.export_all(session)
