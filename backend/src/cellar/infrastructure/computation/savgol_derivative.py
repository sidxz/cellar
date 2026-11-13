"""Savitzky-Golay first derivative of a curve, resampled on its own median spacing
(capped at 4 points per input point)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.signal import savgol_filter

from cellar.domain.screening_assay.curve_derivative import DerivativeCurve


class SavgolCurveDerivative:
    """Implements ``CurveDerivativeService``."""

    def derivative(
        self, x: Sequence[float], y: Sequence[float], *, window: float
    ) -> DerivativeCurve:
        order = np.argsort(x)
        xs, ys = np.asarray(x, float)[order], np.asarray(y, float)[order]
        xs, first = np.unique(xs, return_index=True)
        ys = ys[first]
        if len(xs) < 2:  # no spacing to differentiate over; NaN cannot go in JSON
            return DerivativeCurve(x=(), y=())
        step = float(np.median(np.diff(xs)))  # the curve's own spacing; no instrument constant
        # Evenly spaced over the curve's range, at most 4 points per input point, so an
        # unevenly sampled curve cannot ask for an unbounded grid.
        size = min(round((xs[-1] - xs[0]) / step) + 1, 4 * len(xs))
        grid = np.linspace(xs[0], xs[-1], size)
        step = float(grid[1] - grid[0])
        yi = np.interp(grid, xs, ys)
        if len(grid) < 5:
            d = np.gradient(yi, step)
        else:
            n = max(5, round(window / step) | 1)  # odd, above the polynomial order
            n = min(n, len(grid) if len(grid) % 2 else len(grid) - 1)
            d = savgol_filter(yi, n, 2, deriv=1, delta=step)
        return DerivativeCurve(tuple(grid.tolist()), tuple(d.tolist()))
