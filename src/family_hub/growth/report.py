"""Growth reports as in the earlier growth app: PDF (printable), self-contained HTML and CSV."""

import csv
import html
import io
import math
from collections.abc import Callable
from datetime import date

import matplotlib as mpl
from matplotlib.axes import Axes
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.config import get_settings
from family_hub.core import service as core_service
from family_hub.core.schemas import PersonRead
from family_hub.growth import service
from family_hub.growth.chart import (
    PERCENTILE_COLORS,
    PERCENTILE_DASH,
    PRIMARY,
    SDS_PERCENTILES,
    SHOWN_PERCENTILES,
    TYPE_COLORS,
    age_axis,
    growth_chart,
    sds_chart,
    type_label,
    velocity_chart,
)
from family_hub.growth.metrics import age_months, growth_velocity
from family_hub.growth.models import UNITS, MeasurementType
from family_hub.growth.reference import PERCENTILE_Z, Reference
from family_hub.growth.schemas import MeasurementRead
from family_hub.growth.service import to_points
from family_hub.ui import i18n
from family_hub.ui.i18n import t

A4_PORTRAIT = (8.27, 11.69)
TABLE_ROWS_PER_PAGE = 38
MPL_DASH = {"solid": "-", "dash": "--", "dot": ":"}
GRID_COLOR = "#e5e7eb"
MUTED = "#6b7280"


class ReportData(BaseModel):
    """Everything a report shows for one child."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    person: PersonRead
    measurements: list[MeasurementRead]
    references: dict[MeasurementType, Reference | None]
    age_now: float

    @property
    def types(self) -> list[MeasurementType]:
        """Measurement types present, in display order."""
        present = {m.type for m in self.measurements}
        return [measurement_type for measurement_type in MeasurementType if measurement_type in present]

    def of_type(self, measurement_type: MeasurementType) -> list[MeasurementRead]:
        """Measurements of one type, oldest first."""
        return [m for m in self.measurements if m.type is measurement_type]

    def file_stem(self) -> str:
        """File name without extension."""
        safe = "".join(c if c.isalnum() else "_" for c in self.person.name)
        return f"{t('growth.title').lower()}_{safe}_{date.today():%Y%m%d}"

    def header_lines(self) -> list[str]:
        """Name, birth date, sex and creation date."""
        lines = [self.person.name]
        if self.person.birth_date:
            lines.append(t("growth.born", date=i18n.day(self.person.birth_date)))
        if self.person.sex:
            lines.append(t(f"core.sex.{self.person.sex.value}"))
        lines.append(t("growth.report.created", date=i18n.day(date.today())))
        return lines


async def load(session: AsyncSession, person_id: int) -> ReportData:
    """Collect the report data of a child.

    Raises:
        core_service.PersonNotFoundError: If the person does not exist.
        service.NotAChildError: If the person has no child profile.
    """
    person = await core_service.get_person(session, person_id)
    measurements = await service.list_measurements(session, person_id)
    references = {
        measurement_type: service.reference_for(person, measurement_type) for measurement_type in MeasurementType
    }
    age_now = age_months(person.birth_date, date.today()) if person.birth_date else 0.0
    return ReportData(person=person, measurements=measurements, references=references, age_now=age_now)


def reference_note() -> str:
    """Source of the reference data, if configured."""
    name = get_settings().growth_reference_name
    return t("growth.report.reference", name=name) if name else t("growth.report.reference_unnamed")


def _optional(value: float | None, digits: int, *, sign: bool = False) -> str:
    if value is None:
        return "–"
    return i18n.signed(value, digits) if sign else i18n.number(value, digits)


def table_rows(data: ReportData) -> tuple[list[str], list[list[str]]]:
    """Header and rows of the measurement table, formatted for the current language."""
    header = [
        t("common.date"),
        t("growth.age"),
        t("growth.report.type"),
        t("growth.report.value"),
        t("growth.report.unit"),
        t("growth.report.percentile"),
        "SDS",
        t("growth.at_doctor_short"),
    ]
    rows = [
        [
            i18n.day(m.measured_on),
            i18n.format_age(int(m.age_months)),
            type_label(m.type),
            i18n.number(m.value, 2),
            m.unit,
            _optional(m.percentile, 1),
            _optional(m.z, 2, sign=True),
            t("growth.report.yes") if m.official else t("growth.report.no"),
        ]
        for m in sorted(data.measurements, key=lambda m: (m.measured_on, list(MeasurementType).index(m.type)))
    ]
    return header, rows


def build_csv(data: ReportData) -> bytes:
    """All measurements incl. age in months; German uses `;` and decimal commas, as spreadsheets expect."""
    german = i18n.language() is i18n.Language.DE
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";" if german else ",")
    header, rows = table_rows(data)
    header.insert(2, t("growth.age_months"))
    writer.writerow(header)
    measurements = sorted(data.measurements, key=lambda m: (m.measured_on, list(MeasurementType).index(m.type)))
    for row, measurement in zip(rows, measurements, strict=True):
        row.insert(2, i18n.number(measurement.age_months, 2))
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def _mpl_color(color: str) -> str | tuple[float, float, float, float]:
    if not color.startswith("rgba"):
        return color
    r, g, b, a = (float(part) for part in color[color.index("(") + 1 : -1].split(","))
    return r / 255, g / 255, b / 255, a


def _style(ax: Axes) -> None:
    ax.grid(True, color=GRID_COLOR, linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _x_max(data: ReportData) -> float:
    ages = [m.age_months for m in data.measurements] or [0.0]
    return max(max(ages), data.age_now) * 1.1 + 1


def _draw_growth(ax: Axes, data: ReportData, measurement_type: MeasurementType) -> None:
    x_max = _x_max(data)
    factor, title = age_axis(x_max)
    reference = data.references.get(measurement_type)
    own = data.of_type(measurement_type)
    if reference is not None:
        ages = reference.ages / factor
        ax.fill_between(
            ages, reference.percentiles["P25"], reference.percentiles["P75"], color=(0.39, 0.45, 0.55, 0.12)
        )
        for column in SHOWN_PERCENTILES:
            ax.plot(
                ages,
                reference.percentiles[column],
                color=_mpl_color(PERCENTILE_COLORS[column]),
                linestyle=MPL_DASH[PERCENTILE_DASH[column]],
                linewidth=1.4 if column == "P50" else 0.9,
            )
            visible = reference.ages <= x_max
            if visible.any():
                ax.annotate(
                    column,
                    (x_max / factor, float(reference.percentiles[column][visible][-1])),
                    xytext=(3, 0),
                    textcoords="offset points",
                    fontsize=7,
                    va="center",
                    color=PRIMARY if column == "P50" else MUTED,
                    annotation_clip=False,
                )
    color = TYPE_COLORS[measurement_type]
    ax.plot(
        [m.age_months / factor for m in own],
        [m.value for m in own],
        color=color,
        linewidth=1.6,
        marker="o",
        markersize=3.5,
        label=t("growth.measurement"),
    )
    home = [m for m in own if not m.official]
    if home:
        ax.scatter(
            [m.age_months / factor for m in home],
            [m.value for m in home],
            s=55,
            facecolors="none",
            edgecolors=color,
            linewidths=1.2,
            label=t("growth.at_home"),
            zorder=3,
        )
    values = [m.value for m in own]
    if reference is not None:
        visible = reference.ages <= x_max
        values += [
            float(reference.percentiles["P3"][visible].min()),
            float(reference.percentiles["P97"][visible].max()),
        ]
    if values:
        span = max(values) - min(values) or 1.0
        ax.set_ylim(min(values) - 0.05 * span, max(values) + 0.05 * span)
    ax.set_xlim(0, x_max / factor)
    ax.set_title(type_label(measurement_type), loc="left", fontsize=11, fontweight="bold")
    ax.set_xlabel(title)
    ax.set_ylabel(f"{type_label(measurement_type)} ({UNITS[measurement_type]})")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    _style(ax)


def _draw_velocity(ax: Axes, data: ReportData, measurement_type: MeasurementType) -> bool:
    bins = growth_velocity(to_points(data.of_type(measurement_type)), data.references.get(measurement_type))
    if not bins:
        return False
    factor, title = age_axis(_x_max(data))
    color = TYPE_COLORS[measurement_type]
    starts = [b.age_start / factor for b in bins]
    widths = [(b.age_end - b.age_start) / factor for b in bins]
    ax.bar(
        starts,
        [b.velocity for b in bins],
        width=widths,
        align="edge",
        color=color,
        alpha=0.75,
        edgecolor=color,
        linewidth=0.8,
        label=t("growth.child"),
    )
    references = [(s, s + w, b.reference_velocity) for s, w, b in zip(starts, widths, bins, strict=True)]
    finite = [r for r in references if math.isfinite(r[2])]
    if finite:
        ax.hlines(
            [r[2] for r in finite],
            [r[0] for r in finite],
            [r[1] for r in finite],
            color=PRIMARY,
            linewidth=2.2,
            label=t("growth.child_on_p50"),
        )
    ax.set_xlim(0, _x_max(data) / factor)
    ax.set_title(
        f"{t('growth.tab.velocity')}: {type_label(measurement_type)}", loc="left", fontsize=11, fontweight="bold"
    )
    ax.set_xlabel(title)
    ax.set_ylabel(t("growth.per_month", unit=UNITS[measurement_type]))
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    _style(ax)
    return True


def _draw_sds(ax: Axes, data: ReportData) -> None:
    x_max = _x_max(data)
    factor, title = age_axis(x_max)
    for column in SDS_PERCENTILES:
        ax.axhline(
            PERCENTILE_Z[column],
            color=_mpl_color(PERCENTILE_COLORS[column]),
            linestyle=MPL_DASH[PERCENTILE_DASH[column]],
            linewidth=1.4 if column == "P50" else 0.9,
        )
    with_z = [m for m in data.measurements if m.z is not None]
    for measurement_type in data.types:
        own = [m for m in with_z if m.type is measurement_type]
        if own:
            ax.plot(
                [m.age_months / factor for m in own],
                [m.z for m in own],
                color=TYPE_COLORS[measurement_type],
                marker="o",
                markersize=3.5,
                linewidth=1.6,
                label=type_label(measurement_type),
            )
    z_max = max([2.5, *[abs(m.z) + 0.3 for m in with_z if m.z is not None]])
    ax.set_xlim(0, x_max / factor)
    ax.set_ylim(-z_max, z_max)
    ax.set_title(t("growth.tab.sds"), loc="left", fontsize=11, fontweight="bold")
    ax.set_xlabel(title)
    ax.set_ylabel("SDS")
    if with_z:
        ax.legend(loc="upper left", fontsize=8, frameon=False)
    _style(ax)


def _has_sds(data: ReportData) -> bool:
    return any(m.z is not None for m in data.measurements)


def _static_svg(draw: Callable[..., object], data: ReportData, *args: object) -> str:
    fig = Figure(figsize=(10, 5))
    with mpl.rc_context({"font.size": 9}):
        draw(fig.add_subplot(), data, *args)
        fig.tight_layout()
        buffer = io.StringIO()
        fig.savefig(buffer, format="svg")
    svg = buffer.getvalue()
    return svg[svg.index("<svg") :]


HTML_STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1100px; color: #1f2328; padding: 0 1rem; }
h1 { margin-bottom: .25rem; font-weight: 600; } .meta { color: #59636e; margin-bottom: 2rem; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { border-bottom: 1px solid #d1d9e0; padding: .35rem .5rem; text-align: right; }
th:nth-child(-n+3), td:nth-child(-n+3) { text-align: left; }
th { background: #f6f8fa; } .note { color: #59636e; font-size: .85rem; }
.chart { break-inside: avoid; margin-bottom: 2rem; } .static svg { width: 100%; height: auto; }
html:not(.js) .interactive, .js .static { display: none; }
"""


def build_html(data: ReportData) -> bytes:
    """Self-contained report with interactive charts (Plotly embedded once) and static SVG fallbacks."""
    charts = []
    for measurement_type in data.types:
        reference = data.references.get(measurement_type)
        own = data.of_type(measurement_type)
        charts.append(
            (
                type_label(measurement_type),
                growth_chart(own, measurement_type, reference, data.age_now),
                _static_svg(_draw_growth, data, measurement_type),
            )
        )
        bins = growth_velocity(to_points(own), reference)
        if bins:
            charts.append(
                (
                    f"{t('growth.tab.velocity')}: {type_label(measurement_type)}",
                    velocity_chart(bins, measurement_type),
                    _static_svg(_draw_velocity, data, measurement_type),
                )
            )
    if _has_sds(data):
        charts.append((t("growth.tab.sds"), sds_chart(data.measurements, data.age_now), _static_svg(_draw_sds, data)))

    sections = []
    for index, (title, figure, svg) in enumerate(charts):
        interactive = figure.to_html(full_html=False, include_plotlyjs=index == 0, config={"displaylogo": False})
        sections.append(
            f'<section class="chart"><h2>{html.escape(title)}</h2>'
            f'<div class="static">{svg}</div><div class="interactive">{interactive}</div></section>'
        )
    header, rows = table_rows(data)
    table = (
        "<table><thead><tr>"
        + "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in rows)
        + "</tbody></table>"
    )
    title = f"{t('growth.title')} – {data.person.name}"
    meta = " · ".join(html.escape(line) for line in data.header_lines())
    page = f"""<!doctype html>
<html lang="{i18n.language().value}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>document.documentElement.classList.add("js")</script>
<title>{html.escape(title)}</title><style>{HTML_STYLE}</style></head>
<body><h1>{html.escape(title)}</h1><div class="meta">{meta}</div>
{"".join(sections)}
<h2>{html.escape(t("growth.measurements"))}</h2>{table}
<p class="note">{html.escape(reference_note())}</p>
</body></html>"""
    return page.encode("utf-8")


def _page(data: ReportData, number: int) -> Figure:
    fig = Figure(figsize=A4_PORTRAIT)
    fig.text(0.07, 0.965, f"{t('growth.title')} – {data.person.name}", fontsize=15, fontweight="bold")
    fig.text(0.07, 0.945, "   ·   ".join(data.header_lines()), fontsize=8, color=MUTED)
    fig.text(0.93, 0.02, str(number), fontsize=8, color=MUTED, ha="right")
    return fig


def build_pdf(data: ReportData) -> bytes:
    """Printable A4 report: growth and velocity chart per type, SDS chart, measurement table."""
    buffer = io.BytesIO()
    number = 0
    with (
        mpl.rc_context({"font.size": 9}),
        PdfPages(buffer, metadata={"Title": f"{t('growth.title')} – {data.person.name}"}) as pdf,
    ):
        for measurement_type in data.types:
            number += 1
            fig = _page(data, number)
            _draw_growth(fig.add_axes((0.1, 0.5, 0.82, 0.4)), data, measurement_type)
            velocity_ax = fig.add_axes((0.1, 0.08, 0.82, 0.32))
            if not _draw_velocity(velocity_ax, data, measurement_type):
                velocity_ax.remove()
            pdf.savefig(fig)

        if _has_sds(data):
            number += 1
            fig = _page(data, number)
            _draw_sds(fig.add_axes((0.1, 0.5, 0.82, 0.4)), data)
            fig.text(0.1, 0.42, reference_note(), fontsize=8, color=MUTED, wrap=True)
            pdf.savefig(fig)

        header, rows = table_rows(data)
        for start in range(0, max(len(rows), 1), TABLE_ROWS_PER_PAGE):
            number += 1
            fig = _page(data, number)
            ax = fig.add_axes((0.07, 0.06, 0.86, 0.85))
            ax.axis("off")
            ax.set_title(t("growth.measurements"), loc="left", fontsize=11, fontweight="bold")
            chunk = rows[start : start + TABLE_ROWS_PER_PAGE]
            if chunk:
                table = ax.table(cellText=chunk, colLabels=header, loc="upper left", cellLoc="right")
                table.auto_set_font_size(False)
                table.set_fontsize(8)
                table.scale(1, 1.25)
                for (row, column), cell in table.get_celld().items():
                    cell.set_edgecolor("#d1d9e0")
                    cell.visible_edges = "B"
                    if column in (0, 1, 2, 4):
                        cell.get_text().set_horizontalalignment("left")
                    if row == 0:
                        cell.set_text_props(fontweight="bold")
            pdf.savefig(fig)
    return buffer.getvalue()
