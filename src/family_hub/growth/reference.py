"""Growth reference tables (LMS method, Cole & Green), loaded from a directory outside the repository.

File per type and sex, e.g. `weight-girls.csv`, semicolon separated:
`age;unit;P3;P10;P25;P50;P75;P90;P97;L;S` with unit `Monate` or `Jahre`. Missing L/S are fitted from the
percentiles. For each age: z = ((x / M) ** L - 1) / (L * S), or ln(x / M) / S for L = 0.
"""

import csv
import math
from functools import cache
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict

from family_hub.core.models import Sex
from family_hub.growth.models import MeasurementType

PERCENTILE_Z = {
    "P3": -1.880794,
    "P10": -1.281552,
    "P25": -0.674490,
    "P50": 0.0,
    "P75": 0.674490,
    "P90": 1.281552,
    "P97": 1.880794,
}
AGE_UNIT_MONTHS = {"Monate": 1.0, "Jahre": 12.0}
SEX_FILE_NAMES = {Sex.FEMALE: "girls", Sex.MALE: "boys"}
_L_GRID = np.linspace(-3.0, 3.0, 6001)
_L_EPSILON = 1e-9


class Reference(BaseModel):
    """Reference for one type and sex; arrays are aligned with `ages` (months, ascending)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    ages: np.ndarray
    percentiles: dict[str, np.ndarray]
    lms_l: np.ndarray
    lms_m: np.ndarray
    lms_s: np.ndarray

    def lms(self, age_months: float) -> tuple[float, float, float]:
        """L, M, S at an age, linear between reference ages and clamped to the table."""
        return (
            float(np.interp(age_months, self.ages, self.lms_l)),
            float(np.interp(age_months, self.ages, self.lms_m)),
            float(np.interp(age_months, self.ages, self.lms_s)),
        )

    def z_score(self, value: float, age_months: float) -> float:
        """SDS of a value at an age."""
        l_, m, s = self.lms(age_months)
        if abs(l_) < _L_EPSILON:
            return math.log(value / m) / s
        return ((value / m) ** l_ - 1) / (l_ * s)

    def median(self, age_months: float) -> float:
        """P50 at an age."""
        return self.lms(age_months)[1]

    @property
    def max_age(self) -> float:
        """Oldest age covered, in months."""
        return float(self.ages[-1])


def z_to_percentile(z: float) -> float:
    """Percentile (0-100) of a standard normal z-score."""
    return 50 * (1 + math.erf(z / math.sqrt(2)))


def _value_at_z(l_: np.ndarray, m: float, s: np.ndarray, z: np.ndarray) -> np.ndarray:
    safe_l = np.where(np.abs(l_) < _L_EPSILON, 1.0, l_)
    box_cox = m * np.power(np.maximum(1 + safe_l * s * z, 1e-12), 1 / safe_l)
    return np.where(np.abs(l_) < _L_EPSILON, m * np.exp(s * z), box_cox)


def fit_l_s(percentiles: dict[str, float]) -> tuple[float, float]:
    """Least-squares L and S for one age from its published percentiles (M = P50)."""
    m = percentiles["P50"]
    names = [name for name in PERCENTILE_Z if name != "P50"]
    values = np.array([percentiles[name] for name in names])[None, :]
    z = np.array([PERCENTILE_Z[name] for name in names])[None, :]
    l_ = _L_GRID[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        implied_s = np.where(np.abs(l_) < _L_EPSILON, np.log(values / m) / z, ((values / m) ** l_ - 1) / (l_ * z))
    s = implied_s.mean(axis=1, keepdims=True)
    errors = ((_value_at_z(l_, m, s, z) - values) ** 2).sum(axis=1)
    best = int(np.nanargmin(errors))
    return float(_L_GRID[best]), float(s[best, 0])


def parse_reference(path: Path) -> Reference:
    """Read one reference file.

    Raises:
        ValueError: If the file has an unknown age unit or no rows.
    """
    rows: dict[float, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file, delimiter=";"):
            if row["unit"] not in AGE_UNIT_MONTHS:
                raise ValueError(f"Unknown age unit {row['unit']!r} in {path}")
            rows.setdefault(float(row["age"]) * AGE_UNIT_MONTHS[row["unit"]], row)
    if not rows:
        raise ValueError(f"No rows in {path}")

    ages = sorted(rows)
    percentiles = {name: np.array([float(rows[age][name]) for age in ages]) for name in PERCENTILE_Z}
    lms_l, lms_s = [], []
    for index, age in enumerate(ages):
        l_text, s_text = rows[age].get("L") or "", rows[age].get("S") or ""
        if l_text.strip() and s_text.strip():
            lms_l.append(float(l_text))
            lms_s.append(float(s_text))
        else:
            fitted = fit_l_s({name: float(values[index]) for name, values in percentiles.items()})
            lms_l.append(fitted[0])
            lms_s.append(fitted[1])
    return Reference(
        ages=np.array(ages),
        percentiles=percentiles,
        lms_l=np.array(lms_l),
        lms_m=percentiles["P50"],
        lms_s=np.array(lms_s),
    )


@cache
def _load(path: Path) -> Reference | None:
    return parse_reference(path) if path.is_file() else None


def load_reference(directory: Path | None, measurement_type: MeasurementType, sex: Sex) -> Reference | None:
    """Return the reference for a type and sex, or None if no file is configured."""
    if directory is None:
        return None
    return _load(directory / f"{measurement_type.value}-{SEX_FILE_NAMES[sex]}.csv")
