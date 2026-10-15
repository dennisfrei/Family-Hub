import numpy as np
import pytest
from scipy.interpolate import Akima1DInterpolator, PchipInterpolator, interp1d, make_interp_spline

from family_hub.fever import interpolation


def _series(seed: int, n: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = 1.79e9 + np.cumsum(rng.uniform(600, 6 * 3600, n))
    y = np.round(rng.uniform(36.0, 40.5, n), 1)
    if n > 4:
        y[2] = y[3]
    return x, y


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("n", [2, 3, 4, 5, 8, 13])
def test_matches_scipy(seed: int, n: int) -> None:
    x, y = _series(seed, n)
    xs = np.linspace(x[0], x[-1], 150)

    np.testing.assert_allclose(interpolation.pchip(x, y)(xs), PchipInterpolator(x, y)(xs), atol=1e-9)
    np.testing.assert_allclose(interpolation.linear(x, y)(xs), interp1d(x, y)(xs), atol=1e-9)
    if n >= interpolation.MIN_AKIMA_POINTS or n == 2:
        np.testing.assert_allclose(interpolation.akima(x, y)(xs), Akima1DInterpolator(x, y)(xs), atol=1e-9)
    if n >= interpolation.MIN_SPLINE_POINTS:
        np.testing.assert_allclose(interpolation.spline(x, y)(xs), make_interp_spline(x, y, k=3)(xs), atol=1e-7)


def test_passes_through_points() -> None:
    x, y = _series(1, 6)

    for curve in (interpolation.pchip, interpolation.akima, interpolation.spline, interpolation.linear):
        np.testing.assert_allclose(curve(x, y)(x), y, atol=1e-9)
