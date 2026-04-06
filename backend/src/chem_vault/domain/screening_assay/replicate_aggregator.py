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

from returns.result import Failure, Result, Success

from chem_vault.domain.screening_assay.enums import ReadoutAggregation
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.shared.errors import DomainError, ValidationError


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
        ``Success(list[AggregatedValue])`` — one entry per group.

        ``Failure(ValidationError)`` — when GEOMETRIC_MEAN is requested and any
        value in a group is <= 0 (logarithm undefined for non-positive values).
    """

    def aggregate(
        self,
        readouts: list[ReadoutData],
        aggregation: ReadoutAggregation,
    ) -> Result[list[AggregatedValue], DomainError]:
        """Aggregate replicate readouts using the specified strategy.

        Args:
            readouts: Raw ReadoutData entities from a run.
            aggregation: Which aggregation method to apply.

        Returns:
            Success with list of AggregatedValue, or Failure on domain error.
        """
        if aggregation == ReadoutAggregation.NONE:
            return Success([])

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

            agg_result = self._apply(values, aggregation)
            if isinstance(agg_result, Failure):
                # Propagate failure with context about which group failed
                err = agg_result.failure()
                return Failure(
                    ValidationError(
                        f"GEOMETRIC_MEAN requires all values > 0 "
                        f"(molecule_id={molecule_id}, "
                        f"readout_definition_id={readout_definition_id}): {err.message}"
                    )
                )

            aggregated = agg_result.unwrap()
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

        return Success(results)

    # ------------------------------------------------------------------
    # Internal: strategy dispatch
    # ------------------------------------------------------------------

    @staticmethod
    def _apply(
        values: list[float],
        aggregation: ReadoutAggregation,
    ) -> Result[float, DomainError]:
        """Apply a single aggregation strategy to a list of values."""
        if aggregation == ReadoutAggregation.MEAN:
            return Success(statistics.mean(values))

        if aggregation == ReadoutAggregation.MEDIAN:
            return Success(statistics.median(values))

        if aggregation == ReadoutAggregation.GEOMETRIC_MEAN:
            non_positive = [v for v in values if v <= 0]
            if non_positive:
                return Failure(
                    ValidationError(
                        f"GEOMETRIC_MEAN requires all values > 0; "
                        f"found non-positive: {non_positive}"
                    )
                )
            geo_mean = math.exp(statistics.mean(math.log(v) for v in values))
            return Success(geo_mean)

        if aggregation == ReadoutAggregation.MIN:
            return Success(float(min(values)))

        if aggregation == ReadoutAggregation.MAX:
            return Success(float(max(values)))

        # Defensive: unknown strategy — treat as MEAN
        return Success(statistics.mean(values))
