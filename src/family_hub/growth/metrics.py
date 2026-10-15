"""Growth metrics as in the earlier growth app: fractional age, growth velocity per age bin."""

from datetime import date

import numpy as np
from pydantic import BaseModel, ConfigDict

from family_hub.growth.reference import Reference

AVERAGE_DAYS_PER_MONTH = 365.2425 / 12
INFANT_MONTHS = 24
MIN_INTERVAL_DAYS_INFANT = 28
MIN_INTERVAL_DAYS_CHILD = 90
BIN_MONTHS_INFANT = 1
BIN_MONTHS_CHILD = 6
MIN_BIN_COVERAGE = 0.5


def age_months(birth_date: date, on: date) -> float:
    """Age in average months (fractional)."""
    return (on - birth_date).days / AVERAGE_DAYS_PER_MONTH


class Point(BaseModel):
    """A measurement reduced to what the velocity needs."""

    model_config = ConfigDict(frozen=True)

    measured_on: date
    age_months: float
    value: float


class VelocityBin(BaseModel):
    """Growth per month within one age bin, compared with a child on P50."""

    model_config = ConfigDict(frozen=True)

    age_start: float
    age_end: float
    start_date: date
    end_date: date
    velocity: float
    reference_velocity: float


def _bin_edges(max_age: float) -> np.ndarray:
    infant = np.arange(0, INFANT_MONTHS, BIN_MONTHS_INFANT)
    child = np.arange(INFANT_MONTHS, max(max_age, INFANT_MONTHS) + BIN_MONTHS_CHILD, BIN_MONTHS_CHILD)
    return np.concatenate([infant, child]).astype(float)


def _spaced(points: list[Point]) -> list[Point]:
    kept = [points[0]]
    for point in points[1:]:
        last = kept[-1]
        min_days = MIN_INTERVAL_DAYS_INFANT if last.age_months < INFANT_MONTHS else MIN_INTERVAL_DAYS_CHILD
        if (point.measured_on - last.measured_on).days >= min_days:
            kept.append(point)
    return kept


def growth_velocity(points: list[Point], reference: Reference | None) -> list[VelocityBin]:
    """Growth per month in fixed age bins (monthly below 2 years, half-yearly after that).

    Close measurements are thinned out (4 weeks below 2 years, 3 months after), values are interpolated at the
    bin edges, and bins covered less than half are left out.
    """
    if len(points) < 2:
        return []
    spaced = _spaced(sorted(points, key=lambda p: p.measured_on))
    if len(spaced) < 2:
        return []
    ages = np.array([p.age_months for p in spaced])
    values = np.array([p.value for p in spaced])
    edges = _bin_edges(float(ages[-1]))
    bins = []
    for age_start, age_end in zip(edges[:-1], edges[1:], strict=True):
        lo, hi = max(age_start, ages[0]), min(age_end, ages[-1])
        if hi - lo < MIN_BIN_COVERAGE * (age_end - age_start):
            continue
        start_value, end_value = np.interp([lo, hi], ages, values)
        reference_velocity = (reference.median(hi) - reference.median(lo)) / (hi - lo) if reference else float("nan")
        bins.append(
            VelocityBin(
                age_start=float(age_start),
                age_end=float(age_end),
                start_date=spaced[int(np.searchsorted(ages, lo, side="right")) - 1].measured_on,
                end_date=spaced[int(np.searchsorted(ages, hi, side="left"))].measured_on,
                velocity=float((end_value - start_value) / (hi - lo)),
                reference_velocity=float(reference_velocity),
            )
        )
    return bins
