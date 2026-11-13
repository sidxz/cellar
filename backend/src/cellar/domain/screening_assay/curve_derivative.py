"""Smoothed first derivative of a measured curve: protocol and result type (pure domain)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

DEFAULT_WINDOW_FRACTION = 0.05


@dataclass(frozen=True)
class DerivativeCurve:
    x: tuple[float, ...]
    y: tuple[float, ...]


def default_window(x_ranges: Sequence[tuple[float, float]]) -> float:
    """5% of the widest (max - min) of the given x ranges."""
    return DEFAULT_WINDOW_FRACTION * max(hi - lo for lo, hi in x_ranges)


@runtime_checkable
class CurveDerivativeService(Protocol):
    def derivative(
        self, x: Sequence[float], y: Sequence[float], *, window: float
    ) -> DerivativeCurve: ...
