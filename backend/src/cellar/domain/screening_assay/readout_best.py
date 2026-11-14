"""Which of a compound's values stands for it on a readout.

A potency is better low, a plain signal is read high, and a thermal shift is
read by its size in either direction: a -8.5 °C shift must not lose to +1.4.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from cellar.domain.screening_assay.melt_window import MeltMeasure
from cellar.domain.shared.enums import Qualifier


class BestDirection(StrEnum):
    HIGH = "high"
    LOW = "low"
    MAGNITUDE = "magnitude"


def best_direction(data_type: str, melt_measure: str | None) -> BestDirection:
    """``data_type`` and the melt measure as stored (strings), so read models can call it."""
    if melt_measure == MeltMeasure.LOWEST_SHIFT_CONCENTRATION:
        return BestDirection.LOW
    if melt_measure is not None:
        return BestDirection.MAGNITUDE
    if data_type == "dose_response":
        return BestDirection.LOW
    return BestDirection.HIGH


def pick_best(
    values: Sequence[tuple[float, Qualifier]], direction: BestDirection
) -> tuple[float, Qualifier] | None:
    """The value (with its qualifier) that stands for the compound."""
    if not values:
        return None
    if direction is BestDirection.LOW:
        return min(values, key=lambda v: v[0])
    if direction is BestDirection.MAGNITUDE:
        return max(values, key=lambda v: (abs(v[0]), v[0]))
    return max(values, key=lambda v: v[0])


def best_of_range(low: float | None, high: float | None, direction: BestDirection) -> float | None:
    """The same choice from a group's minimum and maximum (what SQL aggregates give)."""
    if low is None or high is None:
        return None
    if direction is BestDirection.LOW:
        return low
    if direction is BestDirection.MAGNITUDE:
        return high if abs(high) >= abs(low) else low
    return high
