"""Candidate peaks found in a trace: protocol and result type (pure domain)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

MAX_CANDIDATES = 6


class PeakDirection(StrEnum):
    RISING = "rising"
    FALLING = "falling"


@dataclass(frozen=True)
class PeakCandidate:
    value: float  # °C, rounded to 2 decimals
    direction: PeakDirection  # whether the signal rises or falls through the peak
    strength: float  # how far it stands out, in units of the trace's own noise


@runtime_checkable
class PeakDetectionService(Protocol):
    def candidates(
        self, x: Sequence[float], y: Sequence[float], *, window: float
    ) -> tuple[PeakCandidate, ...]:
        """Strongest first, at most ``MAX_CANDIDATES``; ``window`` is the smoothing width."""
        ...
