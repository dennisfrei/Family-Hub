"""Trend chart of systolic and diastolic values."""

from zoneinfo import ZoneInfo

import plotly.graph_objects as go

from family_hub.blood_pressure.schemas import ReadingRead

SYSTOLIC_COLOR = "#ef4444"
DIASTOLIC_COLOR = "#2563eb"


def blood_pressure_chart(
    readings: list[ReadingRead],
    tz: ZoneInfo,
    *,
    limits: tuple[int, int],
    dark: bool = False,
    labels: tuple[str, str] = ("SYS", "DIA"),
    day_format: str = "%d.%m.",
) -> go.Figure:
    """Build the trend for readings sorted oldest first; `limits` are drawn as dashed lines (systolic, diastolic)."""
    times = [r.measured_at.astimezone(tz) for r in readings]
    fig = go.Figure()
    for label, color, values, limit in (
        (labels[0], SYSTOLIC_COLOR, [r.systolic for r in readings], limits[0]),
        (labels[1], DIASTOLIC_COLOR, [r.diastolic for r in readings], limits[1]),
    ):
        fig.add_trace(
            go.Scatter(
                x=times,
                y=values,
                name=label,
                mode="lines+markers",
                line={"color": color, "width": 2},
                marker={"size": 7},
                hovertemplate=f"<b>%{{y}} mmHg</b><br>%{{x|{day_format} %H:%M}}<extra>{label}</extra>",
            )
        )
        fig.add_hline(y=limit, line_dash="dash", line_color=color, line_width=1, opacity=0.5)
    fig.update_layout(
        yaxis={"title": "mmHg"},
        xaxis={"tickformat": day_format},
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "y": 1.15},
        margin={"l": 40, "r": 10, "t": 20, "b": 30},
        height=240,
        autosize=True,
    )
    return fig
