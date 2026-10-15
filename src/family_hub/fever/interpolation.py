"""Smoothing for the fever curve with numpy only: PCHIP, Akima, cubic spline (not-a-knot) and linear.

The results match SciPy's `PchipInterpolator`, `Akima1DInterpolator`, `make_interp_spline(k=3)` and `interp1d`.
"""

from collections.abc import Callable

import numpy as np

type Curve = Callable[[np.ndarray], np.ndarray]

AKIMA_BREAK = 1e-9
MIN_SPLINE_POINTS = 4
MIN_AKIMA_POINTS = 3


def _segments(x: np.ndarray, xs: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(x, xs, side="right") - 1, 0, len(x) - 2)


def _hermite(x: np.ndarray, y: np.ndarray, slopes: np.ndarray) -> Curve:
    def evaluate(xs: np.ndarray) -> np.ndarray:
        i = _segments(x, xs)
        h = x[i + 1] - x[i]
        t = (xs - x[i]) / h
        t2, t3 = t * t, t * t * t
        return (
            (2 * t3 - 3 * t2 + 1) * y[i]
            + (t3 - 2 * t2 + t) * h * slopes[i]
            + (-2 * t3 + 3 * t2) * y[i + 1]
            + (t3 - t2) * h * slopes[i + 1]
        )

    return evaluate


def _pchip_edge(h0: float, h1: float, m0: float, m1: float) -> float:
    d = ((2 * h0 + h1) * m0 - h0 * m1) / (h0 + h1)
    if np.sign(d) != np.sign(m0):
        return 0.0
    if np.sign(m0) != np.sign(m1) and abs(d) > abs(3 * m0):
        return 3 * m0
    return d


def pchip(x: np.ndarray, y: np.ndarray) -> Curve:
    """Shape-preserving piecewise cubic (Fritsch-Carlson with Moler's end points)."""
    h = np.diff(x)
    m = np.diff(y) / h
    if len(x) == 2:
        return _hermite(x, y, np.array([m[0], m[0]]))
    slopes = np.zeros_like(y)
    w1 = 2 * h[1:] + h[:-1]
    w2 = h[1:] + 2 * h[:-1]
    flat = (np.sign(m[1:]) != np.sign(m[:-1])) | (m[1:] == 0) | (m[:-1] == 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        harmonic = (w1 / m[:-1] + w2 / m[1:]) / (w1 + w2)
        slopes[1:-1] = np.where(flat, 0.0, 1.0 / harmonic)
    slopes[0] = _pchip_edge(h[0], h[1], m[0], m[1])
    slopes[-1] = _pchip_edge(h[-1], h[-2], m[-1], m[-2])
    return _hermite(x, y, slopes)


def akima(x: np.ndarray, y: np.ndarray) -> Curve:
    """Akima's sub-spline (1970); two points give a straight line."""
    if len(x) == 2:
        m = (y[1] - y[0]) / (x[1] - x[0])
        return _hermite(x, y, np.array([m, m]))
    m = np.empty(len(x) + 3)
    m[2:-2] = np.diff(y) / np.diff(x)
    m[1] = 2 * m[2] - m[3]
    m[0] = 2 * m[1] - m[2]
    m[-2] = 2 * m[-3] - m[-4]
    m[-1] = 2 * m[-2] - m[-3]
    slopes = 0.5 * (m[3:] + m[:-3])
    dm = np.abs(np.diff(m))
    f1, f2 = dm[2:], dm[:-2]
    f12 = f1 + f2
    defined = f12 > AKIMA_BREAK * f12.max()
    slopes[defined] = m[1:-2][defined] + (f2[defined] / f12[defined]) * (m[2:-1][defined] - m[1:-2][defined])
    return _hermite(x, y, slopes)


def spline(x: np.ndarray, y: np.ndarray) -> Curve:
    """Interpolating cubic spline with not-a-knot ends; needs at least four points."""
    n = len(x)
    h = np.diff(x)
    d = np.diff(y) / h
    a = np.zeros((n, n))
    b = np.zeros(n)
    a[0, :3] = [h[1], -(h[0] + h[1]), h[0]]
    a[-1, -3:] = [h[-1], -(h[-2] + h[-1]), h[-2]]
    for i in range(1, n - 1):
        a[i, i - 1 : i + 2] = [h[i - 1], 2 * (h[i - 1] + h[i]), h[i]]
        b[i] = 6 * (d[i] - d[i - 1])
    second = np.linalg.solve(a, b)

    def evaluate(xs: np.ndarray) -> np.ndarray:
        i = _segments(x, xs)
        hi = h[i]
        left, right = x[i + 1] - xs, xs - x[i]
        return (
            second[i] * left**3 / (6 * hi)
            + second[i + 1] * right**3 / (6 * hi)
            + (y[i] / hi - second[i] * hi / 6) * left
            + (y[i + 1] / hi - second[i + 1] * hi / 6) * right
        )

    return evaluate


def linear(x: np.ndarray, y: np.ndarray) -> Curve:
    """Straight lines between the points."""
    return lambda xs: np.interp(xs, x, y)
