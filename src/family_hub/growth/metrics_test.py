from datetime import date, timedelta

import pytest

from family_hub.growth.metrics import Point, age_months, growth_velocity

BIRTH = date(2022, 1, 1)


def _points(days: list[int], per_day: float) -> list[Point]:
    return [
        Point(
            measured_on=BIRTH + timedelta(days=d),
            age_months=age_months(BIRTH, BIRTH + timedelta(days=d)),
            value=50 + per_day * d,
        )
        for d in days
    ]


def test_age_months() -> None:
    assert age_months(BIRTH, date(2023, 1, 1)) == pytest.approx(11.99, abs=0.02)


def test_monthly_bins_below_two_years() -> None:
    bins = growth_velocity(_points(list(range(0, 200, 30)), per_day=0.1), None)

    assert [b.age_start for b in bins][:3] == [0.0, 1.0, 2.0]
    assert all(b.velocity == pytest.approx(0.1 * 30.436875, rel=1e-3) for b in bins)


def test_close_measurements_are_thinned() -> None:
    bins = growth_velocity(_points([0, 3, 6, 9], per_day=0.1), None)

    assert bins == []


def test_half_year_bins_after_two_years() -> None:
    bins = growth_velocity(_points(list(range(800, 1600, 100)), per_day=0.02), None)

    assert {b.age_end - b.age_start for b in bins} == {6.0}
