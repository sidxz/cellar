"""PlateNormalizer — pure domain computation service for well-value normalization.

No I/O. No external dependencies. All normalization strategies are pure
functions that operate on lists of Well entities and a dict of raw values.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass

from chem_vault.domain.screening_assay.enums import ReadoutNormalization, WellType
from chem_vault.domain.screening_assay.run import Well
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Output value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedValue:
    """A single normalized readout value for one well."""

    well_id: uuid.UUID
    molecule_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    original_value: float
    normalized_value: float


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


class PlateNormalizer:
    """Applies a normalization strategy to a plate's raw values.

    All methods are synchronous and pure (no side effects).
    Only wells with ``well_type == WellType.SAMPLE`` receive a normalized
    value; control and blank wells are used only as reference points.

    Returns:
        ``list[NormalizedValue]`` — normalized values for all sample
        wells that have a raw value entry.

    Raises:
        ``ValidationError`` — when required controls are missing,
        raw values are absent for controls, or a mathematical constraint is
        violated (e.g., zero denominator, zero stdev).
    """

    def normalize(
        self,
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
        normalization: ReadoutNormalization,
    ) -> list[NormalizedValue]:
        """Dispatch to the appropriate normalization strategy."""
        if normalization == ReadoutNormalization.NONE:
            return []
        if normalization == ReadoutNormalization.PERCENT_INHIBITION:
            return self._percent_inhibition(wells, raw_values)
        if normalization == ReadoutNormalization.PERCENT_ACTIVATION:
            return self._percent_activation(wells, raw_values)
        if normalization == ReadoutNormalization.PERCENT_CONTROL:
            return self._percent_control(wells, raw_values)
        if normalization == ReadoutNormalization.Z_SCORE:
            return self._z_score(wells, raw_values)
        # Defensive: unknown strategy — treat as NONE
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _values_for_type(
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
        well_type: WellType,
    ) -> list[float]:
        """Collect raw values for all wells of a given type that have data."""
        return [
            raw_values[w.id]
            for w in wells
            if w.well_type == well_type and w.id in raw_values
        ]

    @staticmethod
    def _sample_wells(
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
    ) -> list[Well]:
        """Return sample wells that have a raw value entry."""
        return [
            w
            for w in wells
            if w.well_type == WellType.SAMPLE and w.id in raw_values
        ]

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _percent_inhibition(
        self,
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
    ) -> list[NormalizedValue]:
        """100 * (1 - (sample - blank_mean) / (neg_ctrl_mean - blank_mean)).

        Requires: negative_control wells.
        Optional: blank wells (default blank_mean = 0.0).
        """
        neg_vals = self._values_for_type(wells, raw_values, WellType.NEGATIVE_CONTROL)
        if not neg_vals:
            raise ValidationError(
                "PERCENT_INHIBITION requires at least one negative control well with data"
            )

        blank_vals = self._values_for_type(wells, raw_values, WellType.BLANK)
        blank_mean = statistics.mean(blank_vals) if blank_vals else 0.0
        neg_ctrl_mean = statistics.mean(neg_vals)

        denominator = neg_ctrl_mean - blank_mean
        if denominator == 0.0:
            raise ValidationError(
                "PERCENT_INHIBITION: denominator (neg_ctrl_mean - blank_mean) is zero"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = 100.0 * (1.0 - (sample - blank_mean) / denominator)
            results.append(
                NormalizedValue(
                    well_id=w.id,
                    molecule_id=None,
                    batch_id=w.batch_id,
                    original_value=sample,
                    normalized_value=normalized,
                )
            )
        return results

    def _percent_activation(
        self,
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
    ) -> list[NormalizedValue]:
        """100 * ((sample - neg_ctrl_mean) / (pos_ctrl_mean - neg_ctrl_mean)).

        Requires: positive_control AND negative_control wells.
        """
        neg_vals = self._values_for_type(wells, raw_values, WellType.NEGATIVE_CONTROL)
        pos_vals = self._values_for_type(wells, raw_values, WellType.POSITIVE_CONTROL)

        if not neg_vals:
            raise ValidationError(
                "PERCENT_ACTIVATION requires at least one negative control well with data"
            )
        if not pos_vals:
            raise ValidationError(
                "PERCENT_ACTIVATION requires at least one positive control well with data"
            )

        neg_ctrl_mean = statistics.mean(neg_vals)
        pos_ctrl_mean = statistics.mean(pos_vals)

        denominator = pos_ctrl_mean - neg_ctrl_mean
        if denominator == 0.0:
            raise ValidationError(
                "PERCENT_ACTIVATION: denominator (pos_ctrl_mean - neg_ctrl_mean) is zero"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = 100.0 * (sample - neg_ctrl_mean) / denominator
            results.append(
                NormalizedValue(
                    well_id=w.id,
                    molecule_id=None,
                    batch_id=w.batch_id,
                    original_value=sample,
                    normalized_value=normalized,
                )
            )
        return results

    def _percent_control(
        self,
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
    ) -> list[NormalizedValue]:
        """100 * (sample / neg_ctrl_mean).

        Requires: negative_control wells.
        """
        neg_vals = self._values_for_type(wells, raw_values, WellType.NEGATIVE_CONTROL)
        if not neg_vals:
            raise ValidationError(
                "PERCENT_CONTROL requires at least one negative control well with data"
            )

        neg_ctrl_mean = statistics.mean(neg_vals)
        if neg_ctrl_mean == 0.0:
            raise ValidationError(
                "PERCENT_CONTROL: neg_ctrl_mean is zero — cannot divide"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = 100.0 * sample / neg_ctrl_mean
            results.append(
                NormalizedValue(
                    well_id=w.id,
                    molecule_id=None,
                    batch_id=w.batch_id,
                    original_value=sample,
                    normalized_value=normalized,
                )
            )
        return results

    def _z_score(
        self,
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
    ) -> list[NormalizedValue]:
        """(sample - neg_ctrl_mean) / neg_ctrl_stdev.

        Requires: at least 2 negative control wells (stdev requires n >= 2).
        Raises if stdev is zero.
        """
        neg_vals = self._values_for_type(wells, raw_values, WellType.NEGATIVE_CONTROL)
        if len(neg_vals) < 2:
            raise ValidationError(
                "Z_SCORE requires at least 2 negative control wells with data"
            )

        neg_ctrl_mean = statistics.mean(neg_vals)
        neg_ctrl_stdev = statistics.stdev(neg_vals)

        if neg_ctrl_stdev == 0.0:
            raise ValidationError(
                "Z_SCORE: negative control stdev is zero — cannot compute Z-score"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = (sample - neg_ctrl_mean) / neg_ctrl_stdev
            results.append(
                NormalizedValue(
                    well_id=w.id,
                    molecule_id=None,
                    batch_id=w.batch_id,
                    original_value=sample,
                    normalized_value=normalized,
                )
            )
        return results
