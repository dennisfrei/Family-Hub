"""Fever curve chart with colored temperature zones, as in the earlier fever app."""

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

import numpy as np
import plotly.graph_objects as go

from family_hub.fever import interpolation
from family_hub.fever.schemas import ReadingRead
from family_hub.fever.thresholds import Thresholds

LINE_COLOR = "#2563eb"
NORMAL_FILL = "rgba(34, 197, 94, 0.3)"
ELEVATED_FILL = "rgba(249, 115, 22, 0.3)"
FEVER_FILL = "rgba(239, 68, 68, 0.3)"


class Interpolation(StrEnum):
    """Curve smoothing between readings."""

    PCHIP = "pchip"
    AKIMA = "akima"
    SPLINE = "spline"
    LINEAR = "linear"


INTERPOLATION_LABELS = {
    Interpolation.PCHIP: "PCHIP",
    Interpolation.AKIMA: "Akima",
    Interpolation.SPLINE: "Spline",
    Interpolation.LINEAR: "Linear",
}


def _interpolator(method: Interpolation, x: np.ndarray, y: np.ndarray) -> interpolation.Curve:
    if method is Interpolation.SPLINE and len(x) >= interpolation.MIN_SPLINE_POINTS:
        return interpolation.spline(x, y)
    if method is Interpolation.AKIMA and len(x) >= interpolation.MIN_AKIMA_POINTS:
        return interpolation.akima(x, y)
    if method is Interpolation.PCHIP:
        return interpolation.pchip(x, y)
    return interpolation.linear(x, y)


def _band(fig: go.Figure, x: list[datetime], bottom: list[float], top: list[float], color: str) -> None:
    hidden = {"mode": "lines", "line": {"width": 0}, "showlegend": False, "hoverinfo": "skip"}
    fig.add_trace(go.Scatter(x=x, y=bottom, **hidden))
    fig.add_trace(go.Scatter(x=x, y=top, fill="tonexty", fillcolor=color, **hidden))


def _smooth_curve(
    fig: go.Figure,
    readings: list[ReadingRead],
    thresholds: Thresholds,
    method: Interpolation,
    floor: float,
    tz: ZoneInfo,
) -> None:
    unique = {r.measured_at.timestamp(): r.temperature for r in readings}
    if len(unique) < 2:
        return
    x = np.array(sorted(unique))
    y = np.array([unique[t] for t in x])
    x_smooth = np.linspace(x.min(), x.max(), min(150, max(50, len(x) * 10)))
    y_smooth = _interpolator(method, x, y)(x_smooth)
    times = [datetime.fromtimestamp(t, tz) for t in x_smooth]
    count = len(times)

    _band(fig, times, [floor] * count, [min(t, thresholds.elevated) for t in y_smooth], NORMAL_FILL)
    elevated_tops = [max(min(t, thresholds.fever), thresholds.elevated) for t in y_smooth]
    _band(fig, times, [thresholds.elevated] * count, elevated_tops, ELEVATED_FILL)
    _band(fig, times, [thresholds.fever] * count, [max(t, thresholds.fever) for t in y_smooth], FEVER_FILL)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=y_smooth,
            mode="lines",
            line={"color": LINE_COLOR, "width": 2},
            showlegend=False,
            hoverinfo="skip",
        )
    )


def fever_chart(
    readings: list[ReadingRead],
    thresholds: Thresholds,
    *,
    tz: ZoneInfo,
    interpolation: Interpolation = Interpolation.PCHIP,
    dark: bool = False,
    labels: tuple[str, str, str] = ("Fieber", "Erhöht", "Temperatur (°C)"),
) -> go.Figure:
    """Build the fever curve for readings sorted oldest first."""
    temperatures = [r.temperature for r in readings]
    floor = min([*temperatures, 36.0]) - 0.5
    ceiling = max([*temperatures, 40.0]) + 0.5

    fig = go.Figure()
    _smooth_curve(fig, readings, thresholds, interpolation, floor, tz)
    fig.add_trace(
        go.Scatter(
            x=[r.measured_at.astimezone(tz) for r in readings],
            y=temperatures,
            mode="markers",
            marker={"size": 10, "color": LINE_COLOR, "line": {"width": 2, "color": "white"}},
            hovertemplate="<b>%{y:.1f} °C</b><br>%{x|%d.%m. %H:%M}<br>%{text}<extra></extra>",
            text=[r.note or "" for r in readings],
            showlegend=False,
        )
    )
    if readings:
        for value, color, label in (
            (thresholds.fever, "#ef4444", labels[0]),
            (thresholds.elevated, "#f97316", labels[1]),
        ):
            fig.add_hline(
                y=value,
                line_dash="dash",
                line_color=color,
                line_width=1,
                annotation_text=label,
                annotation_position="right",
            )
    fig.update_layout(
        yaxis={"range": [floor, ceiling], "title": labels[2]},
        xaxis={"tickformat": "%d.%m.\n%H:%M"},
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 40, "r": 60, "t": 20, "b": 40},
        height=320,
        autosize=True,
    )
    return fig
