"""Temperature windows: which melting steps feed a Tm / ΔTm readout."""

from __future__ import annotations

import math
import uuid
from collections.abc import Collection, Sequence
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
    # Descriptive values per batch over a concentration series (no fit).
    MAX_DELTA_TM = "max_delta_tm"
    LOWEST_SHIFT_CONCENTRATION = "lowest_shift_concentration"
    DELTA_TM_AT_CONCENTRATION = "delta_tm_at_concentration"

    @property
    def is_series(self) -> bool:
        """One value per batch, not per position."""
        return self not in PER_POSITION_MEASURES


PER_POSITION_MEASURES: frozenset[MeltMeasure] = frozenset({MeltMeasure.TM, MeltMeasure.DELTA_TM})


def _positive(value: float | None, what: str) -> None:
    if value is not None and not (math.isfinite(value) and value > 0):
        raise ValidationError(f"{what} must be a number above zero")


@dataclass(frozen=True)
class MeltReadoutConfig:
    """A readout computed from melting steps inside a temperature window."""

    window: str
    measure: MeltMeasure
    channel_key: str
    low: float
    high: float
    # Lowest shifting concentration: |ΔTm| above this (°C) counts as a shift.
    threshold: float | None = None
    # ΔTm at a stated concentration, in the protocol's dose unit.
    concentration: float | None = None

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
        wants_threshold = self.measure is MeltMeasure.LOWEST_SHIFT_CONCENTRATION
        wants_concentration = self.measure is MeltMeasure.DELTA_TM_AT_CONCENTRATION
        if (self.threshold is not None) != wants_threshold:
            raise ValidationError(
                "A shift threshold is set on, and only on, a lowest shifting concentration"
            )
        if (self.concentration is not None) != wants_concentration:
            raise ValidationError(
                "A concentration is set on, and only on, a ΔTm at a stated concentration"
            )
        _positive(self.threshold, "The shift threshold")
        _positive(self.concentration, "The concentration")

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "measure": self.measure.value,
            "channel_key": self.channel_key,
            "low": self.low,
            "high": self.high,
            **({"threshold": self.threshold} if self.threshold is not None else {}),
            **({"concentration": self.concentration} if self.concentration is not None else {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MeltReadoutConfig:
        return cls(
            window=d["window"],
            measure=MeltMeasure(d["measure"]),
            channel_key=d["channel_key"],
            low=float(d["low"]),
            high=float(d["high"]),
            threshold=None if d.get("threshold") is None else float(d["threshold"]),
            concentration=None if d.get("concentration") is None else float(d["concentration"]),
        )

    @property
    def key(self) -> tuple[MeltMeasure, float | None, float | None]:
        """What must differ between two readouts of one window."""
        return (self.measure, self.threshold, self.concentration)

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


class NamedBy(StrEnum):
    """How a position's Tm in a window was chosen."""

    RANGE = "range"
    ASSIGNMENT = "assignment"


@dataclass(frozen=True)
class StepFact:
    """One melting step, as the naming rule sees it."""

    id: uuid.UUID
    well_id: uuid.UUID
    channel_key: str
    value: float
    counts: bool
    assigned_window: str | None


@dataclass(frozen=True)
class WindowPosition:
    well_id: uuid.UUID
    well_type: WellType
    steps: tuple[StepFact, ...]  # counted steps on the window's channel, sorted by value


@dataclass(frozen=True)
class PositionWindowResult:
    well_id: uuid.UUID
    tm: float | None
    delta_tm: float | None
    flags: tuple[WindowFlag, ...]
    # Set together with ``tm``: how the Tm was named, and the step that supplied it.
    named_by: NamedBy | None = None
    step_id: uuid.UUID | None = None


@dataclass(frozen=True)
class WindowResult:
    low: float
    high: float
    reference_tm: float | None
    reference_count: int
    positions: tuple[PositionWindowResult, ...]
    flags: tuple[WindowFlag, ...]


def evaluate_window(
    window: str,
    low: float,
    high: float,
    positions: Sequence[WindowPosition],
    windows_on_signal: Collection[str],
) -> WindowResult:
    """Tm per position and its shift from the reference mean.

    A step assigned to ``window`` names the Tm whatever its value. Otherwise the
    Tm is the step inside [low, high] that is not assigned to another current
    window of the signal (``windows_on_signal``; any other name is stale and
    counts as no assignment). One candidate gives the Tm; none or several give a flag.
    """
    tms: list[tuple[WindowPosition, StepFact | None, NamedBy, tuple[WindowFlag, ...]]] = []
    for p in positions:
        if p.well_type == WellType.BLANK:
            continue
        named_by = NamedBy.ASSIGNMENT
        candidates = [s for s in p.steps if s.assigned_window == window]
        if not candidates:
            named_by = NamedBy.RANGE
            candidates = [
                s
                for s in p.steps
                if s.assigned_window not in windows_on_signal and low <= s.value <= high
            ]
        if not candidates:
            tms.append((p, None, named_by, (WindowFlag.NO_STEP,)))
        elif len(candidates) == 1:
            tms.append((p, candidates[0], named_by, ()))
        else:
            tms.append((p, None, named_by, (WindowFlag.SEVERAL_STEPS,)))
    ref_values = [
        s.value for p, s, _, _ in tms if p.well_type == WellType.REFERENCE and s is not None
    ]
    reference_tm = sum(ref_values) / len(ref_values) if ref_values else None
    results = tuple(
        PositionWindowResult(
            well_id=p.well_id,
            tm=s.value if s else None,
            delta_tm=(
                s.value - reference_tm
                if s is not None and reference_tm is not None and p.well_type != WellType.REFERENCE
                else None
            ),
            flags=flags,
            named_by=named_by if s else None,
            step_id=s.id if s else None,
        )
        for p, s, named_by, flags in tms
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
    steps: Sequence[StepFact],
    channel_key: str,
    traced: Collection[tuple[uuid.UUID, str]],
) -> list[WindowPosition]:
    """Non-blank positions with a trace on one channel, with their counted steps there, sorted.

    ``traced`` holds the (well id, channel key) pairs that have a trace.
    """
    by_well: dict[uuid.UUID, list[StepFact]] = {}
    for s in steps:
        if s.counts and s.channel_key == channel_key:
            by_well.setdefault(s.well_id, []).append(s)
    return [
        WindowPosition(
            well_id, well_type, tuple(sorted(by_well.get(well_id, ()), key=lambda s: s.value))
        )
        for well_id, well_type in wells
        if well_type != WellType.BLANK and (well_id, channel_key) in traced
    ]


def outside_every_window(
    positions: Sequence[WindowPosition], windows: Sequence[tuple[str, float, float]]
) -> tuple[uuid.UUID, ...]:
    """Ids of the counted steps no window takes: not assigned to one of ``windows``
    (name, low, high: the windows of the positions' channel) and inside none of them."""
    names = {name for name, _, _ in windows}
    return tuple(
        s.id
        for p in positions
        for s in p.steps
        if s.assigned_window not in names
        and not any(low <= s.value <= high for _, low, high in windows)
    )
