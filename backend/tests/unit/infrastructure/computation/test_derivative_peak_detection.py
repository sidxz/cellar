"""Unit tests for finding candidate peaks in a trace from its smoothed derivative.

Every trace is synthetic: sigmoid steps on a sloped baseline plus seeded Gaussian noise.
"""

from __future__ import annotations

import math
import random

import pytest

from cellar.domain.screening_assay.peak_detection import (
    MAX_CANDIDATES,
    PeakCandidate,
    PeakDetectionService,
    PeakDirection,
)
from cellar.infrastructure.computation.derivative_peak_detection import DerivativePeakDetection
from cellar.infrastructure.computation.savgol_derivative import SavgolCurveDerivative

X = [25 + 0.057 * i for i in range(1223)]  # 25 to 94.65 °C
WINDOW = 3.5


def _trace(
    steps: list[tuple[float, float]],
    *,
    seed: int = 7,
    noise: float = 0.01,
    slope: float = 0.002,
    width: float = 1.2,
) -> list[float]:
    """Steps given as (midpoint, height); a negative height lowers the signal."""
    rng = random.Random(seed)
    return [
        slope * t
        + sum(height / (1 + math.exp(-(t - mid) / width)) for mid, height in steps)
        + rng.gauss(0, noise)
        for t in X
    ]


def _find(y: list[float], *, window: float = WINDOW) -> tuple[PeakCandidate, ...]:
    return DerivativePeakDetection(SavgolCurveDerivative()).candidates(X, y, window=window)


def test_implements_the_domain_protocol():
    assert isinstance(DerivativePeakDetection(SavgolCurveDerivative()), PeakDetectionService)


def test_one_rising_step_is_found_at_its_midpoint():
    (found,) = _find(_trace([(60.0, 1.0)]))
    assert abs(found.value - 60.0) < 0.3
    assert found.direction is PeakDirection.RISING
    assert found.value == round(found.value, 2)
    assert math.isfinite(found.strength) and found.strength > 0


def test_one_falling_step_is_found_as_falling():
    (found,) = _find(_trace([(60.0, -1.0)]))
    assert abs(found.value - 60.0) < 0.3
    assert found.direction is PeakDirection.FALLING


def test_two_steps_give_two_candidates_strongest_first():
    # The weaker step lowers the signal: both directions count, not only the dominant one.
    strong, weak = _find(_trace([(50.0, 1.0), (72.0, -0.4)]))
    assert abs(strong.value - 50.0) < 0.3 and strong.direction is PeakDirection.RISING
    assert abs(weak.value - 72.0) < 0.3 and weak.direction is PeakDirection.FALLING
    assert strong.strength > weak.strength


def test_the_valley_between_two_rising_steps_is_not_a_falling_step():
    found = _find(_trace([(48.0, 1.0), (72.0, 0.6)], width=1.5))
    assert [(round(c.value), c.direction) for c in found] == [
        (48, PeakDirection.RISING),
        (72, PeakDirection.RISING),
    ]
    # A real fall between two rises is kept.
    found = _find(_trace([(40.0, 1.0), (58.0, -0.6), (76.0, 1.0)]))
    assert sorted((round(c.value), c.direction) for c in found) == [
        (40, PeakDirection.RISING),
        (58, PeakDirection.FALLING),
        (76, PeakDirection.RISING),
    ]


def test_steps_do_not_raise_their_own_noise():
    # Two broad steps leave no quiet stretch in the derivative. Their strength still follows
    # their height: ten times the step over the same noise, ten times the strength.
    low = _find(_trace([(48.0, 1.0), (72.0, 0.8)], width=2.5))
    high = _find(_trace([(48.0, 10.0), (72.0, 8.0)], width=2.5))
    assert [round(c.value) for c in low] == [round(c.value) for c in high] == [48, 72]
    assert [c.strength for c in high] == pytest.approx([10 * c.strength for c in low], rel=0.1)


@pytest.mark.parametrize("seed", range(40))
def test_noise_only_gives_none(seed: int):
    assert _find(_trace([], seed=seed)) == ()


def test_step_at_the_scan_edge_is_dropped():
    # Midpoints inside one smoothing window of each end of the scan.
    assert _find(_trace([(92.5, 1.0)])) == ()
    assert _find(_trace([(27.0, -1.0)])) == ()


def test_at_most_six():
    steps = [(30.0 + 8 * i, 1.0 + 0.1 * i) for i in range(8)]
    found = _find(_trace(steps, width=0.3), window=1.0)
    assert len(found) == MAX_CANDIDATES == 6
    strengths = [c.strength for c in found]
    assert strengths == sorted(strengths, reverse=True)
    assert {round(c.value) for c in found} == {46, 54, 62, 70, 78, 86}  # the six largest


def test_scaling_and_offset_do_not_change_the_result():
    y = _trace([(50.0, 1.0), (72.0, -0.4)])
    plain, changed = _find(y), _find([250.0 * v + 1000.0 for v in y])
    assert [(c.value, c.direction) for c in changed] == [(c.value, c.direction) for c in plain]
    assert [c.strength for c in changed] == pytest.approx([c.strength for c in plain], rel=1e-6)


def test_flat_or_short_trace_gives_none_without_error():
    find = DerivativePeakDetection(SavgolCurveDerivative()).candidates
    assert _find([3.0] * len(X)) == ()  # every value identical: no noise to compare with
    assert _find([0.1 + 0.2] * len(X)) == ()  # the same, with a value floats cannot hold exactly
    assert _find([2 * t + 1 for t in X]) == ()  # a straight line: its derivative is flat
    assert find([], [], window=WINDOW) == ()
    assert find([30.0], [1.0], window=WINDOW) == ()
    assert find([30.0, 30.0, 30.0], [1.0, 2.0, 3.0], window=WINDOW) == ()
    assert find([30.0, 31.0, 32.0], [1.0, 2.0, 4.0], window=WINDOW) == ()
    # Shorter than two smoothing windows: nothing is left once the ends are dropped.
    assert find(X[:100], _trace([(27.0, 1.0)])[:100], window=WINDOW) == ()
    # A gap in the scan (missing rows) and a zero window do not raise.
    y = _trace([(60.0, 1.0)])
    assert isinstance(find(X[:400] + X[500:], y[:400] + y[500:], window=WINDOW), tuple)
    assert isinstance(find(X, y, window=0.0), tuple)
