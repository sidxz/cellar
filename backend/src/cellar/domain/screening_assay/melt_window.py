"""Temperature windows: which melting steps feed a Tm / ΔTm readout."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from cellar.domain.shared.errors import ValidationError

# Kind of a reported instrument value that is a melting step (neutral wording).
STEP_KIND = "transition"
WINDOW_NAME_MAX = 60


class MeltMeasure(StrEnum):
    TM = "tm"
    DELTA_TM = "delta_tm"


@dataclass(frozen=True)
class MeltReadoutConfig:
    """A readout computed from melting steps inside a temperature window."""

    window: str
    measure: MeltMeasure
    channel_key: str
    low: float
    high: float

    def __post_init__(self) -> None:
        window = self.window.strip()
        if not 1 <= len(window) <= WINDOW_NAME_MAX:
            raise ValidationError(
                f"Temperature window name must be 1 to {WINDOW_NAME_MAX} characters"
            )
        channel_key = self.channel_key.strip()
        if not channel_key:
            raise ValidationError("Temperature window channel must not be blank")
        if not (math.isfinite(self.low) and math.isfinite(self.high)):
            raise ValidationError("Temperature window limits must be finite numbers")
        if not self.low < self.high:
            raise ValidationError("Temperature window low limit must be below the high limit")
        object.__setattr__(self, "window", window)
        object.__setattr__(self, "channel_key", channel_key)
        object.__setattr__(self, "measure", MeltMeasure(self.measure))

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "measure": self.measure.value,
            "channel_key": self.channel_key,
            "low": self.low,
            "high": self.high,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MeltReadoutConfig:
        return cls(
            window=d["window"],
            measure=MeltMeasure(d["measure"]),
            channel_key=d["channel_key"],
            low=float(d["low"]),
            high=float(d["high"]),
        )

    def same_window(self, other: MeltReadoutConfig) -> bool:
        return (self.window, self.channel_key, self.low, self.high) == (
            other.window,
            other.channel_key,
            other.low,
            other.high,
        )
