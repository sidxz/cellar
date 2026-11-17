"""Candidate peaks of a trace: the extrema of its smoothed first derivative that stand out
from that derivative's own noise."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.signal import find_peaks

from cellar.domain.screening_assay.curve_derivative import CurveDerivativeService
from cellar.domain.screening_assay.peak_detection import (
    MAX_CANDIDATES,
    PeakCandidate,
    PeakDirection,
)

# ponytail: the calibration point. One threshold for every trace: how many standard
# deviations of the derivative's own noise an extremum must stand out by. Chosen on synthetic
# traces only: noise alone (independent or mildly correlated points, on a flat or a steep
# baseline) never reached 10 in 25,000 traces, while a step 12 times as high as the point
# scatter is found 19 times in 20. Raise it if noise is proposed, lower it if visible steps
# are missed. Measured limit: on real instrument traces clear transitions rate from about 20
# upward and are found. Weak transitions, rating about 4 to 11, are not, and lowering the
# threshold to 5 proposes noise on most traces, so weak transitions need the instrument's
# value, a hand-placed peak or curve fitting.
MIN_STRENGTH = 10.0

# A scatter below this share of the signal's size is float rounding, not noise.
_ROUNDING = 1e-9
_CLIP = 3.0  # deviations beyond which a difference belongs to a step, not to the noise
_WANDER = 3.0  # how many times the noise may exceed what the point scatter alone gives


class DerivativePeakDetection:
    """Implements ``PeakDetectionService``."""

    def __init__(self, derivative: CurveDerivativeService) -> None:
        self._derivative = derivative

    def candidates(
        self, x: Sequence[float], y: Sequence[float], *, window: float
    ) -> tuple[PeakCandidate, ...]:
        curve = self._derivative.derivative(x, y, window=window)
        xs, d = np.asarray(curve.x, float), np.asarray(curve.y, float)
        if len(xs) < 2 or not np.isfinite(d).all():
            return ()
        # The derivative is unreliable within one window of either end: nothing there is a
        # candidate, and nothing there is what a candidate is measured against.
        inside = (xs > xs[0] + window) & (xs < xs[-1] - window)
        xs, d = xs[inside], d[inside]
        if len(xs) < 3:
            return ()  # too short for this smoothing
        noise = self._noise(x, y, xs, d, window)
        if not math.isfinite(noise) or noise <= 0:
            return ()  # flat, or not a number: nothing to measure a peak against
        least = MIN_STRENGTH * noise
        # A step can raise or lower the signal: maxima and minima both count.
        extrema = sorted(_extrema(d, 1.0, least) + _extrema(d, -1.0, least))
        if not extrema:
            return ()
        # The baseline under the steps: the straight line from the foot the first of them has
        # on its left to the foot the last has on its right.
        feet = [extrema[0][3], extrema[-1][4]]
        found = []
        for i, sign, prominence, _, _ in extrema:
            # It has to stand out from its surroundings and, in its own direction, from the
            # baseline: the valley between two rising steps is not a falling step.
            beyond = sign * (d[i] - np.interp(xs[i], xs[feet], d[feet]))
            strength = float(min(prominence, beyond) / noise)
            if strength >= MIN_STRENGTH:
                direction = PeakDirection.RISING if sign > 0 else PeakDirection.FALLING
                found.append(PeakCandidate(round(float(xs[i]), 2), direction, strength))
        found.sort(key=lambda c: (-c.strength, c.value))
        return tuple(found[:MAX_CANDIDATES])

    def _noise(
        self, x: Sequence[float], y: Sequence[float], xs: np.ndarray, d: np.ndarray, window: float
    ) -> float:
        """Standard deviation of the derivative's noise at the scale of the smoothing.

        It starts from the scatter of the measured points carried through the derivative,
        which no step raises: the scatter is each point's distance from the middle of its two
        neighbours, in which the shape of the trace cancels. Noise that wanders more slowly
        than from point to point is larger than that, so the estimate then grows to what the
        derivative itself shows, taking in the differences between points one window apart
        only while they stay within ``_CLIP`` deviations of what it already holds: it settles
        on the quiet part of the scan, away from the steps.
        """
        # ponytail: the growth stops at ``_WANDER`` times the starting value, because steps
        # that leave no quiet stretch would otherwise raise it without end. Two limits follow.
        # Noise that wanders more than that (strongly correlated readings, a trace smoothed
        # before export) is taken for peaks; steps crowding the whole scan are rated up to
        # that much weaker. Past either, the answer is fitting the steps, not a constant.
        order = np.argsort(x)
        raw_x, raw_y = np.asarray(x, float)[order], np.asarray(y, float)[order]
        scatter = math.sqrt(float(np.mean(np.diff(raw_y, 2) ** 2)) / 6)
        if not scatter > _ROUNDING * float(np.max(np.abs(raw_y))):
            return 0.0
        # What a single point of size one does to the derivative, summed in squares, is what
        # scatter of size one does to it.
        point = np.zeros(len(raw_x))
        point[len(raw_x) // 2] = 1.0
        even = np.linspace(raw_x[0], raw_x[-1], len(raw_x))
        carried = np.asarray(self._derivative.derivative(even, point, window=window).y)
        least = scatter * math.sqrt(float(np.sum(carried**2)))

        lag = max(1, int(np.searchsorted(xs, xs[0] + window)))
        if lag >= len(d):
            return least
        apart = d[lag:] - d[:-lag]
        apart = np.abs(apart - np.median(apart)) / math.sqrt(2)
        noise, most = max(least, float(apart.min())), _WANDER * least
        while noise < most:  # ends: each pass takes in more differences, or stops
            wider = 1.4826 * float(np.median(apart[apart <= _CLIP * noise]))
            if not wider > noise:
                break
            noise = wider
        return min(noise, most)


def _extrema(d: np.ndarray, sign: float, least: float) -> list[tuple[int, float, float, int, int]]:
    """The maxima (``sign`` 1) or minima (-1) of ``d`` at least ``least`` prominent, each as
    (index, sign, prominence, index of its foot on the left, index of its foot on the right)."""
    at, measured = find_peaks(sign * d, prominence=least)
    return [
        (i, sign, prominence, left, right)
        for i, prominence, left, right in zip(
            at.tolist(),
            measured["prominences"].tolist(),
            measured["left_bases"].tolist(),
            measured["right_bases"].tolist(),
            strict=True,
        )
    ]
