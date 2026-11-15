"""Report of a person's readings as a standalone HTML page or a PDF."""

import base64
import io
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
from fpdf import FPDF
from fpdf.fonts import FontFace
from matplotlib.dates import AutoDateLocator, DateFormatter, date2num
from matplotlib.figure import Figure

from family_hub.blood_pressure.chart import DIASTOLIC_COLOR, SYSTOLIC_COLOR
from family_hub.blood_pressure.levels import Level
from family_hub.blood_pressure.schemas import ReadingRead
from family_hub.blood_pressure.stats import Average
from family_hub.ui import i18n
from family_hub.ui.i18n import t

FONT = "DejaVu"
FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
FONTS = {"": "DejaVuSans.ttf", "B": "DejaVuSans-Bold.ttf"}
LEVEL_COLORS = {Level.NORMAL: (17, 24, 39), Level.ELEVATED: (194, 110, 0), Level.HIGH: (200, 30, 30)}
COLUMN_WIDTHS = (24, 16, 16, 16, 16, 92)
CHART_SIZE = (7.5, 2.8)
CHART_DPI = 200
MIN_CHART_READINGS = 2

Limits = tuple[tuple[int, int], tuple[int, int]]

i18n.register(
    {
        "bp.report_title": ("Blutdruck {name}", "Blood pressure {name}"),
        "bp.report_range": ("{count} Messungen, {start} bis {end}", "{count} readings, {start} to {end}"),
        "bp.report_limits": (
            "Grenzwerte: erhöht ab {elevated} mmHg, hoch ab {high} mmHg",
            "Limits: elevated from {elevated} mmHg, high from {high} mmHg",
        ),
        "bp.avg_days": ("Ø letzte 7 Tage ({count} Messungen)", "Mean of the last 7 days ({count} readings)"),
        "bp.avg_count": ("Ø letzte {count} Messungen", "Mean of the last {count} readings"),
        "bp.note": ("Notiz", "Note"),
        "bp.pulse_value": ("Puls {value}", "Pulse {value}"),
    }
)


def average_label(average: Average) -> str:
    """Which readings the average covers."""
    return t("bp.avg_days" if average.by_days else "bp.avg_count", count=average.count)


def average_value(average: Average) -> str:
    """The average as `SYS/DIA`, with the pulse if known."""
    pulse = [t("bp.pulse_value", value=average.pulse)] if average.pulse is not None else []
    return " · ".join([f"{average.systolic}/{average.diastolic} mmHg", *pulse])


def chart_png(readings: list[ReadingRead], high: tuple[int, int], tz: ZoneInfo) -> bytes | None:
    """Draw the trend of readings (newest first) with the high limits as dashed lines; None for fewer than two."""
    if len(readings) < MIN_CHART_READINGS:
        return None
    ordered = readings[::-1]
    times = date2num([reading.measured_at.astimezone(tz).replace(tzinfo=None) for reading in ordered])
    figure = Figure(figsize=CHART_SIZE, dpi=CHART_DPI, layout="constrained")
    axes = figure.subplots()
    for key, color, values, limit in (
        ("bp.systolic", SYSTOLIC_COLOR, [reading.systolic for reading in ordered], high[0]),
        ("bp.diastolic", DIASTOLIC_COLOR, [reading.diastolic for reading in ordered], high[1]),
    ):
        axes.plot(times, values, color=color, marker="o", markersize=3, linewidth=1.2, label=t(key))
        axes.axhline(limit, color=color, linestyle="--", linewidth=0.8, alpha=0.6)
    axes.set_ylabel("mmHg")
    axes.grid(alpha=0.3)
    axes.spines[["top", "right"]].set_visible(False)
    axes.xaxis.set_major_locator(AutoDateLocator(maxticks=8))
    axes.xaxis.set_major_formatter(DateFormatter(f"{i18n.short_day_format()}\n%Y"))
    axes.legend(loc="lower left", bbox_to_anchor=(0, 1), ncols=2, frameon=False, fontsize=8)
    axes.tick_params(labelsize=8)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue()


def _summary(readings: list[ReadingRead], average: Average | None, limits: Limits, tz: ZoneInfo) -> list[str]:
    lines = []
    if readings:
        start, end = (i18n.day(reading.measured_at.astimezone(tz)) for reading in (readings[-1], readings[0]))
        lines.append(t("bp.report_range", count=len(readings), start=start, end=end))
    if average is not None:
        lines.append(f"{average_label(average)}: {average_value(average)}")
    elevated, high = (f"{systolic}/{diastolic}" for systolic, diastolic in limits)
    lines.append(t("bp.report_limits", elevated=elevated, high=high))
    return lines


def _header() -> list[str]:
    return [t(key) for key in ("common.date", "common.time", "bp.systolic", "bp.diastolic", "bp.pulse", "bp.note")]


def _cells(reading: ReadingRead, tz: ZoneInfo) -> list[str]:
    local = reading.measured_at.astimezone(tz)
    pulse = "" if reading.pulse is None else str(reading.pulse)
    return [i18n.day(local), f"{local:%H:%M}", str(reading.systolic), str(reading.diastolic), pulse, reading.note or ""]


def to_html(name: str, readings: list[ReadingRead], average: Average | None, limits: Limits, tz: ZoneInfo) -> str:
    """Build a printable page.

    Args:
        name: The person's name.
        readings: Readings, newest first.
        average: Recent average, if there is one.
        limits: Elevated and high limit as (systolic, diastolic), e.g. `((130, 85), (140, 90))`.
        tz: Timezone for dates and times.
    """
    title = escape(t("bp.report_title", name=name))
    rows = []
    for reading in readings:
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in _cells(reading, tz))
        rows.append(f'<tr class="{reading.level.value}">{cells}</tr>')
    summary = "".join(f"<p>{escape(line)}</p>" for line in _summary(readings, average, limits, tz))
    head = "".join(f"<th>{escape(cell)}</th>" for cell in _header())
    png = chart_png(readings, limits[1], tz)
    chart = f'<img alt="" src="data:image/png;base64,{base64.b64encode(png).decode()}">' if png else ""
    style = (
        "body{font-family:system-ui,sans-serif;margin:2rem;color:#111827}"
        "table{border-collapse:collapse;width:100%;margin-top:1rem}"
        "th,td{border-bottom:1px solid #d1d5db;padding:.35rem .5rem;text-align:left}"
        "p{margin:.2rem 0}"
        "img{display:block;width:100%;max-width:60rem;margin-top:1rem}"
        "tr.elevated td:nth-child(3),tr.elevated td:nth-child(4){color:#c26e00;font-weight:600}"
        "tr.high td:nth-child(3),tr.high td:nth-child(4){color:#c81e1e;font-weight:600}"
    )
    return (
        f'<!doctype html><html lang="{i18n.language().value}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>'
        f"<style>{style}</style></head><body><h1>{title}</h1>{summary}{chart}"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"
    )


def to_pdf(name: str, readings: list[ReadingRead], average: Average | None, limits: Limits, tz: ZoneInfo) -> bytes:
    """Build an A4 report; arguments as for `to_html`."""
    pdf = FPDF()
    for style, file_name in FONTS.items():
        pdf.add_font(FONT, style, FONT_DIR / file_name)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title(t("bp.report_title", name=name))
    pdf.add_page()
    pdf.set_font(FONT, "B", 16)
    pdf.cell(0, 10, t("bp.report_title", name=name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 10)
    for line in _summary(readings, average, limits, tz):
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    png = chart_png(readings, limits[1], tz)
    if png:
        pdf.image(io.BytesIO(png), w=pdf.epw)
        pdf.ln(3)
    pdf.set_font(FONT, "", 9)
    with pdf.table(
        col_widths=COLUMN_WIDTHS, text_align="LEFT", borders_layout="HORIZONTAL_LINES", line_height=6
    ) as table:
        header = table.row()
        for cell in _header():
            header.cell(cell)
        for reading in readings:
            row = table.row()
            style = FontFace(color=LEVEL_COLORS[reading.level])
            for index, cell in enumerate(_cells(reading, tz)):
                row.cell(cell, style=style if index in (2, 3) else None)
    return bytes(pdf.output())
