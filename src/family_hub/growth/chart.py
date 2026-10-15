"""Plotly charts as in the earlier growth app: percentile curves, SDS course and growth velocity."""

import numpy as np
import plotly.graph_objects as go

from family_hub.growth.metrics import VelocityBin
from family_hub.growth.models import UNITS, MeasurementType
from family_hub.growth.reference import PERCENTILE_Z, Reference
from family_hub.growth.schemas import MeasurementRead
from family_hub.ui import i18n
from family_hub.ui.i18n import t

PRIMARY = "#1f6f63"
GREY = "148, 163, 184"
PERCENTILE_COLORS = {
    "P3": f"rgba({GREY}, 0.45)",
    "P10": f"rgba({GREY}, 0.65)",
    "P25": f"rgba({GREY}, 0.9)",
    "P50": PRIMARY,
    "P75": f"rgba({GREY}, 0.9)",
    "P90": f"rgba({GREY}, 0.65)",
    "P97": f"rgba({GREY}, 0.45)",
}
PERCENTILE_DASH = {"P3": "dot", "P10": "dot", "P25": "dash", "P50": "solid", "P75": "dash", "P90": "dot", "P97": "dot"}
TYPE_COLORS = {MeasurementType.WEIGHT: "#d97706", MeasurementType.LENGTH: "#2563eb", MeasurementType.HEAD: "#64748b"}
BAND_FILL = "rgba(100, 116, 139, 0.12)"
SHOWN_PERCENTILES = ["P10", "P25", "P50", "P75", "P90"]
SDS_PERCENTILES = ["P3", "P10", "P50", "P90", "P97"]
YEARS_FROM_MONTHS = 24


def _layout(dark: bool, height: int) -> dict[str, object]:
    return {
        "template": "plotly_dark" if dark else "plotly_white",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "separators": ",." if i18n.language() is i18n.Language.DE else ".,",
        "legend": {"orientation": "h", "x": 0.5, "xanchor": "center", "y": 1.02, "yanchor": "bottom"},
        "margin": {"l": 50, "r": 40, "t": 40, "b": 50},
        "height": height,
        "hovermode": "closest",
    }


def type_label(measurement_type: MeasurementType) -> str:
    """Translated name of a measurement type."""
    return t(f"growth.type.{measurement_type.value}")


def age_axis(max_age_months: float) -> tuple[float, str]:
    """Divisor and axis title: months below 2 years, years after that."""
    if max_age_months < YEARS_FROM_MONTHS:
        return 1.0, t("growth.age_months")
    return 12.0, t("growth.age_years")


def _x_range(measurements: list[MeasurementRead], age_now: float) -> tuple[float, float]:
    ages = [m.age_months for m in measurements] or [0.0]
    return 0.0, max(max(ages), age_now) * 1.1 + 1


def _hover(m: MeasurementRead) -> str:
    text = f"{i18n.day(m.measured_on)} ({i18n.format_age(int(m.age_months))}): {i18n.number(m.value, 2)} {m.unit}"
    if m.percentile is not None and m.z is not None:
        text += f" · P{m.percentile:.0f} · SDS {i18n.signed(m.z, 2)}"
    return text


def growth_chart(
    measurements: list[MeasurementRead],
    measurement_type: MeasurementType,
    reference: Reference | None,
    age_now: float,
    *,
    dark: bool = False,
) -> go.Figure:
    """Measurements of one type over age, with the reference percentile curves and the P25–P75 band shaded."""
    x_min, x_max = _x_range(measurements, age_now)
    factor, title = age_axis(x_max)
    color = TYPE_COLORS[measurement_type]
    fig = go.Figure()
    y_limits: list[float] = [m.value for m in measurements]

    if reference is not None:
        ages = reference.ages / factor
        fig.add_trace(
            go.Scatter(
                x=ages,
                y=reference.percentiles["P25"],
                mode="lines",
                line={"width": 0},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=ages,
                y=reference.percentiles["P75"],
                mode="lines",
                line={"width": 0},
                fill="tonexty",
                fillcolor=BAND_FILL,
                showlegend=False,
                hoverinfo="skip",
            )
        )
        for column in SHOWN_PERCENTILES:
            fig.add_trace(
                go.Scatter(
                    x=ages,
                    y=reference.percentiles[column],
                    mode="lines",
                    name=column,
                    line={
                        "color": PERCENTILE_COLORS[column],
                        "width": 2 if column == "P50" else 1,
                        "dash": PERCENTILE_DASH[column],
                    },
                    hovertemplate=f"{column}: %{{y:.2f}}<extra></extra>",
                )
            )
        visible = (reference.ages >= x_min) & (reference.ages <= x_max)
        if visible.any():
            y_limits += [
                float(reference.percentiles["P3"][visible].min()),
                float(reference.percentiles["P97"][visible].max()),
            ]

    fig.add_trace(
        go.Scatter(
            x=[m.age_months / factor for m in measurements],
            y=[m.value for m in measurements],
            mode="lines+markers",
            name=t("growth.measurement"),
            line={"color": color, "width": 3},
            marker={
                "color": [color if m.official else "rgba(0,0,0,0)" for m in measurements],
                "size": [9 if m.official else 11 for m in measurements],
                "line": {"color": color, "width": 2},
            },
            text=[_hover(m) for m in measurements],
            hovertemplate="%{text}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(dark, 420),
        xaxis={"title": title, "range": [x_min / factor, x_max / factor]},
        yaxis={"title": f"{type_label(measurement_type)} ({UNITS[measurement_type]})"},
    )
    if y_limits:
        span = max(y_limits) - min(y_limits) or 1.0
        fig.update_yaxes(range=[min(y_limits) - 0.05 * span, max(y_limits) + 0.05 * span])
    return fig


def sds_chart(measurements: list[MeasurementRead], age_now: float, *, dark: bool = False) -> go.Figure:
    """SDS of all types over age: shows whether the child keeps its percentile channel."""
    x_min, x_max = _x_range(measurements, age_now)
    factor, title = age_axis(x_max)
    fig = go.Figure()
    fig.add_hrect(y0=PERCENTILE_Z["P25"], y1=PERCENTILE_Z["P75"], fillcolor=BAND_FILL, line_width=0)
    for column in SDS_PERCENTILES:
        fig.add_hline(
            y=PERCENTILE_Z[column],
            line={
                "color": PERCENTILE_COLORS[column],
                "width": 2 if column == "P50" else 1,
                "dash": PERCENTILE_DASH[column],
            },
            annotation_text=column,
            annotation_position="right",
        )
    with_z = [m for m in measurements if m.z is not None]
    for measurement_type in MeasurementType:
        own = [m for m in with_z if m.type is measurement_type]
        if not own:
            continue
        fig.add_trace(
            go.Scatter(
                x=[m.age_months / factor for m in own],
                y=[m.z for m in own],
                mode="lines+markers",
                name=type_label(measurement_type),
                line={"color": TYPE_COLORS[measurement_type], "width": 3},
                marker={"size": 8},
                text=[_hover(m) for m in own],
                hovertemplate="%{text}<extra></extra>",
            )
        )
    z_max = max([2.5, *[abs(m.z) + 0.3 for m in with_z if m.z is not None]])
    fig.update_layout(
        **_layout(dark, 360),
        xaxis={"title": title, "range": [x_min / factor, x_max / factor]},
        yaxis={"title": "SDS", "range": [-z_max, z_max], "zeroline": False},
    )
    return fig


def velocity_chart(bins: list[VelocityBin], measurement_type: MeasurementType, *, dark: bool = False) -> go.Figure:
    """Growth per month per age bin (bars) against a child on P50 (segments)."""
    factor, title = age_axis(max([b.age_end for b in bins], default=0.0))
    color = TYPE_COLORS[measurement_type]
    rate = t("growth.per_month", unit=UNITS[measurement_type])
    start = np.array([b.age_start / factor for b in bins])
    end = np.array([b.age_end / factor for b in bins])
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=start,
            width=end - start,
            offset=0,
            y=[b.velocity for b in bins],
            name=t("growth.child"),
            marker={"color": color, "opacity": 0.75, "line": {"color": color, "width": 1}},
            text=[
                f"{i18n.format_age(int(b.age_start))} – {i18n.format_age(int(b.age_end))}: "
                f"{i18n.signed(b.velocity, 2)} {rate}<br>P50: {i18n.signed(b.reference_velocity, 2)} {rate}<br>"
                f"{i18n.day(b.start_date)} – {i18n.day(b.end_date)}"
                for b in bins
            ],
            hovertemplate="%{text}<extra></extra>",
            textposition="none",
        )
    )
    segment_x: list[float | None] = []
    segment_y: list[float | None] = []
    for x0, x1, b in zip(start, end, bins, strict=True):
        if np.isfinite(b.reference_velocity):
            segment_x += [float(x0), float(x1), None]
            segment_y += [b.reference_velocity, b.reference_velocity, None]
    if segment_x:
        fig.add_trace(
            go.Scatter(
                x=segment_x,
                y=segment_y,
                mode="lines",
                name=t("growth.child_on_p50"),
                line={"color": PRIMARY, "width": 3},
            )
        )
    fig.update_layout(
        **_layout(dark, 360), bargap=0, xaxis={"title": title}, yaxis={"title": rate, "rangemode": "tozero"}
    )
    return fig
