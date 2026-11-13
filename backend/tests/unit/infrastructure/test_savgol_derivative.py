"""Unit tests for the Savitzky-Golay curve derivative and the default window."""

from __future__ import annotations

import math
import random

import pytest

from cellar.domain.screening_assay.curve_derivative import default_window
from cellar.infrastructure.computation.savgol_derivative import SavgolCurveDerivative

X = [25 + 0.057 * i for i in range(1223)]


def _peak_x(out) -> float:
    return out.x[max(range(len(out.y)), key=out.y.__getitem__)]


def test_straight_line_has_constant_derivative():
    out = SavgolCurveDerivative().derivative(X, [2 * v + 1 for v in X], window=3.5)
    assert all(abs(v - 2.0) < 1e-6 for v in out.y) and len(out.x) == len(out.y)


def test_sigmoid_derivative_peaks_at_its_midpoint():
    y = [1 / (1 + math.exp(-(v - 60.0))) for v in X]
    out = SavgolCurveDerivative().derivative(X, y, window=3.5)
    assert abs(_peak_x(out) - 60.0) < 0.5


def test_unsorted_and_duplicate_x_are_handled():
    pairs = [(v, 1 / (1 + math.exp(-(v - 60.0)))) for v in X]
    pairs.append(pairs[100])  # one repeated x
    random.Random(1).shuffle(pairs)
    out = SavgolCurveDerivative().derivative(
        [p[0] for p in pairs], [p[1] for p in pairs], window=3.5
    )
    assert abs(_peak_x(out) - 60.0) < 0.5


def test_short_curve_falls_back_to_plain_gradient():
    out = SavgolCurveDerivative().derivative([20.0, 21.0, 22.0], [1.0, 2.0, 4.0], window=3.5)
    assert len(out.x) >= 2 and all(math.isfinite(v) for v in out.y)


def test_output_is_finite():
    y = [math.sin(v) for v in X]
    out = SavgolCurveDerivative().derivative(X, y, window=3.5)
    assert all(math.isfinite(v) for v in out.x + out.y)


def test_default_window_is_five_percent_of_the_widest_range():
    assert default_window([(25.0, 95.0), (25.0, 90.0)]) == pytest.approx(3.5)
