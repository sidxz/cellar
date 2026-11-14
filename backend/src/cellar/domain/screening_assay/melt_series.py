"""Descriptive values of a concentration series, per batch, from one temperature window.

Standard thermal-shift reporting for a series is ΔTm against concentration plus
plain summaries of it; no curve is fitted (fitting a dose-response equation to
Tm against concentration is not physically meaningful, Bai et al. 2019).
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig, WindowResult
from cellar.domain.shared.enums import Qualifier
from cellar.domain.shared.errors import ValidationError

# Two doses typed for the same concentration differ by float noise at most.
_SAME_DOSE = 1e-6


@dataclass(frozen=True)
class SeriesPoint:
    batch_id: uuid.UUID
    concentration: float | None
    delta_tm: float


@dataclass(frozen=True)
class SeriesValue:
    batch_id: uuid.UUID
    value: float
    qualifier: Qualifier
    # The concentration the value belongs to: where Max ΔTm occurred, the
    # lowest shifting concentration itself, or the stated concentration.
    concentration: float | None


def series_points(
    result: WindowResult,
    wells: Mapping[uuid.UUID, tuple[uuid.UUID | None, float | None]],
) -> list[SeriesPoint]:
    """Positions with a ΔTm and a batch; ``wells[id] = (batch_id, dose)``."""
    points = []
    for p in result.positions:
        batch_id, dose = wells.get(p.well_id, (None, None))
        if p.delta_tm is not None and batch_id is not None:
            points.append(SeriesPoint(batch_id, dose, p.delta_tm))
    return points


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _means_by_dose(points: Sequence[SeriesPoint]) -> dict[float | None, float]:
    by_dose: dict[float | None, list[float]] = defaultdict(list)
    for p in points:
        by_dose[p.concentration].append(p.delta_tm)
    return {dose: _mean(ds) for dose, ds in by_dose.items()}


def _max_delta_tm(batch: uuid.UUID, points: Sequence[SeriesPoint]) -> SeriesValue:
    means = _means_by_dose(points)
    # Largest magnitude; on a tie the higher concentration (no concentration ranks lowest).
    dose, mean = max(
        means.items(), key=lambda kv: (abs(kv[1]), -math.inf if kv[0] is None else kv[0])
    )
    return SeriesValue(batch, mean, Qualifier.EQUAL, dose)


def _lowest_shift(
    batch: uuid.UUID, points: Sequence[SeriesPoint], threshold: float
) -> SeriesValue | None:
    dosed = sorted(
        (dose, mean)
        for dose, mean in _means_by_dose(points).items()
        if dose is not None and dose > 0
    )
    if not dosed:
        return None
    for dose, mean in dosed:
        if mean < -threshold or mean > threshold:  # strictly outside, as the "outside" rule
            return SeriesValue(batch, dose, Qualifier.EQUAL, dose)
    highest = dosed[-1][0]
    return SeriesValue(batch, highest, Qualifier.GREATER_THAN, highest)


def _at_concentration(
    batch: uuid.UUID, points: Sequence[SeriesPoint], concentration: float
) -> SeriesValue | None:
    at = [
        p.delta_tm
        for p in points
        if p.concentration is not None
        and math.isclose(p.concentration, concentration, rel_tol=_SAME_DOSE)
    ]
    return SeriesValue(batch, _mean(at), Qualifier.EQUAL, concentration) if at else None


def series_values(config: MeltReadoutConfig, points: Sequence[SeriesPoint]) -> list[SeriesValue]:
    """One value per batch at most, for a series measure; sorted by batch id."""
    if not config.measure.is_series:
        raise ValidationError(f"'{config.measure}' is not a series value")
    by_batch: dict[uuid.UUID, list[SeriesPoint]] = defaultdict(list)
    for p in points:
        by_batch[p.batch_id].append(p)
    out: list[SeriesValue] = []
    for batch in sorted(by_batch, key=str):
        pts = by_batch[batch]
        if config.measure is MeltMeasure.MAX_DELTA_TM:
            value: SeriesValue | None = _max_delta_tm(batch, pts)
        elif config.measure is MeltMeasure.LOWEST_SHIFT_CONCENTRATION:
            value = _lowest_shift(batch, pts, config.threshold)  # type: ignore[arg-type]
        else:
            value = _at_concentration(batch, pts, config.concentration)  # type: ignore[arg-type]
        if value is not None:
            out.append(value)
    return out
