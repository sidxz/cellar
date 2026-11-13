"""Temperature windows: which melting steps feed a Tm / ΔTm readout."""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from cellar.domain.shared.enums import WellType
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


class WindowFlag(StrEnum):
    NO_STEP = "no_step_in_window"
    SEVERAL_STEPS = "several_steps_in_window"
    NO_REFERENCE = "no_reference_value"


@dataclass(frozen=True)
class WindowPosition:
    well_id: uuid.UUID
    well_type: WellType
    steps: tuple[float, ...]  # counted step values on the window's channel


@dataclass(frozen=True)
class PositionWindowResult:
    well_id: uuid.UUID
    tm: float | None
    delta_tm: float | None
    flags: tuple[WindowFlag, ...]


@dataclass(frozen=True)
class WindowResult:
    low: float
    high: float
    reference_tm: float | None
    reference_count: int
    positions: tuple[PositionWindowResult, ...]
    flags: tuple[WindowFlag, ...]


def evaluate_window(low: float, high: float, positions: Sequence[WindowPosition]) -> WindowResult:
    """Tm per position (one step inside [low, high]) and its shift from the reference mean."""
    tms: list[tuple[WindowPosition, float | None, tuple[WindowFlag, ...]]] = []
    for p in positions:
        if p.well_type == WellType.BLANK:
            continue
        inside = [s for s in p.steps if low <= s <= high]
        if not inside:
            tms.append((p, None, (WindowFlag.NO_STEP,)))
        elif len(inside) == 1:
            tms.append((p, inside[0], ()))
        else:
            tms.append((p, None, (WindowFlag.SEVERAL_STEPS,)))
    ref_values = [tm for p, tm, _ in tms if p.well_type == WellType.REFERENCE and tm is not None]
    reference_tm = sum(ref_values) / len(ref_values) if ref_values else None
    results = tuple(
        PositionWindowResult(
            well_id=p.well_id,
            tm=tm,
            delta_tm=(
                tm - reference_tm
                if tm is not None
                and reference_tm is not None
                and p.well_type != WellType.REFERENCE
                else None
            ),
            flags=flags,
        )
        for p, tm, flags in tms
    )
    return WindowResult(
        low=low,
        high=high,
        reference_tm=reference_tm,
        reference_count=len(ref_values),
        positions=results,
        flags=() if ref_values else (WindowFlag.NO_REFERENCE,),
    )


@dataclass(frozen=True)
class StepCountCheck:
    differs: frozenset[uuid.UUID]
    references_differ: bool


def check_step_counts(positions: Sequence[WindowPosition]) -> StepCountCheck:
    """Positions whose number of counted steps differs from the references'."""
    ref_counts = {len(p.steps) for p in positions if p.well_type == WellType.REFERENCE}
    if not ref_counts:
        return StepCountCheck(frozenset(), False)
    if len(ref_counts) > 1:
        return StepCountCheck(frozenset(), True)
    n = next(iter(ref_counts))
    return StepCountCheck(
        frozenset(
            p.well_id
            for p in positions
            if p.well_type not in (WellType.BLANK, WellType.REFERENCE) and len(p.steps) != n
        ),
        False,
    )


def window_positions(
    wells: Sequence[tuple[uuid.UUID, WellType]],
    steps: Sequence[tuple[uuid.UUID, str, float, bool]],
    channel_key: str,
) -> list[WindowPosition]:
    """Non-blank positions with their counted step values on one channel, sorted."""
    by_well: dict[uuid.UUID, list[float]] = {}
    for well_id, key, value, counts in steps:
        if counts and key == channel_key:
            by_well.setdefault(well_id, []).append(value)
    return [
        WindowPosition(well_id, well_type, tuple(sorted(by_well.get(well_id, ()))))
        for well_id, well_type in wells
        if well_type != WellType.BLANK
    ]
