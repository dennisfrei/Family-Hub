"""Fixtures with a synthetic reference table (no real reference data in this repository)."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from family_hub.config import get_settings
from family_hub.growth.reference import PERCENTILE_Z, _load

LMS_L, LMS_S = 0.5, 0.04


def median_at(age_months: float) -> float:
    """Synthetic P50: 50 cm at birth, +2 cm per month, +0.5 cm per month after 2 years."""
    return 50 + 2 * min(age_months, 24) + 0.5 * max(age_months - 24, 0)


def value_at(age_months: float, z: float) -> float:
    """Value with SDS z at an age."""
    return median_at(age_months) * (1 + LMS_L * LMS_S * z) ** (1 / LMS_L)


def write_reference(path: Path, *, fitted_rows: int = 3) -> None:
    """Write a table in the expected format; the first rows have no L/S."""
    rows = [(float(m), "Monate", float(m)) for m in range(22)] + [(y / 2, "Jahre", y * 6.0) for y in range(4, 37)]
    lines = ["age;unit;" + ";".join(PERCENTILE_Z) + ";L;S"]
    for index, (age, unit, months) in enumerate(rows):
        percentiles = ";".join(f"{value_at(months, z):.4f}" for z in PERCENTILE_Z.values())
        lms = ";" if index < fitted_rows else f"{LMS_L};{LMS_S}"
        lines.append(f"{age};{unit};{percentiles};{lms}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_reference(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ignore any reference directory from the environment or `.env`."""
    monkeypatch.setattr(get_settings(), "growth_reference_dir", None)
    _load.cache_clear()
    yield
    _load.cache_clear()


@pytest.fixture
def reference_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Configure a reference directory with length tables for both sexes."""
    for sex in ("girls", "boys"):
        write_reference(tmp_path / f"length-{sex}.csv")
    monkeypatch.setattr(get_settings(), "growth_reference_dir", tmp_path)
    _load.cache_clear()
    yield tmp_path
    _load.cache_clear()
