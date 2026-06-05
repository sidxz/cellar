"""ReplicateAggregator — pure domain computation service for replicate aggregation.

No I/O. No external dependencies. Groups ReadoutData by (molecule_id, readout_definition_id)
and applies the configured aggregation strategy across replicate measurements.
"""

from __future__ import annotations

import math
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass

from cellar.domain.screening_assay.enums import ReadoutAggregation
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.shared.errors import ValidationError

# ---------------------------------------------------------------------------
# Output value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregatedValue:
    """Aggregated result for one (molecule, readout_definition) group."""

    molecule_id: uuid.UUID
    readout_definition_id: uuid.UUID
    value: float
    count: int
    stdev: float | None


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class ReplicateAggregator:
    """Aggregates replicate ReadoutData measurements across a run.

    Groups by ``(molecule_id, readout_definition_id)``, extracts numeric values
    from ``readout.value.value`` (QualifiedValue VO), and applies the chosen
    aggregation strategy.

    ReadoutData entries with ``value is None`` are silently skipped.

    Returns:
        ``list[AggregatedValue]`` — one entry per group.

    Raises:
        ``ValidationError`` — when GEOMETRIC_MEAN is requested and any
        value in a group is <= 0 (logarithm undefined for non-positive values).
    """

    def aggregate(
        self,
        readouts: list[ReadoutData],
        aggregation: ReadoutAggregation,
    ) -> list[AggregatedValue]:
        """Aggregate replicate readouts using the specified strategy.

        Args:
            readouts: Raw ReadoutData entities from a run.
            aggregation: Which aggregation method to apply.

        Returns:
            list of AggregatedValue.

        Raises:
            ValidationError: on domain error (e.g. non-positive values for GEOMETRIC_MEAN).
        """
        if aggregation == ReadoutAggregation.NONE:
            return []

        # Group numeric values by (molecule_id, readout_definition_id)
        groups: dict[tuple[uuid.UUID, uuid.UUID], list[float]] = defaultdict(list)
        for readout in readouts:
            if readout.value is not None:
                groups[(readout.molecule_id, readout.readout_definition_id)].append(
                    readout.value.value
                )

        results: list[AggregatedValue] = []
        for (molecule_id, readout_definition_id), values in groups.items():
            if not values:
                continue

            try:
                aggregated = self._apply(values, aggregation)
            except ValidationError as exc:
                raise ValidationError(
                    f"GEOMETRIC_MEAN requires all values > 0 "
                    f"(molecule_id={molecule_id}, "
                    f"readout_definition_id={readout_definition_id}): {exc.message}"
                ) from exc

            count = len(values)
            stdev = statistics.stdev(values) if count > 1 else None

            results.append(
                AggregatedValue(
                    molecule_id=molecule_id,
                    readout_definition_id=readout_definition_id,
                    value=aggregated,
                    count=count,
                    stdev=stdev,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Internal: strategy dispatch
    # ------------------------------------------------------------------

    @staticmethod
    def _apply(
        values: list[float],
        aggregation: ReadoutAggregation,
    ) -> float:
        """Apply a single aggregation strategy to a list of values."""
        if aggregation == ReadoutAggregation.MEAN:
            return statistics.mean(values)

        if aggregation == ReadoutAggregation.MEDIAN:
            return statistics.median(values)

        if aggregation == ReadoutAggregation.GEOMETRIC_MEAN:
            non_positive = [v for v in values if v <= 0]
            if non_positive:
                raise ValidationError(
                    f"GEOMETRIC_MEAN requires all values > 0; found non-positive: {non_positive}"
                )
            return math.exp(statistics.mean(math.log(v) for v in values))

        if aggregation == ReadoutAggregation.MIN:
            return float(min(values))

        if aggregation == ReadoutAggregation.MAX:
            return float(max(values))

        # Defensive: unknown strategy — treat as MEAN
        return statistics.mean(values)
