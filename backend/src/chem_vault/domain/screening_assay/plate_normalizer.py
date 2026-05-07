"""PlateNormalizer — pure domain computation service for well-value normalization.

No I/O. No external dependencies. All normalization strategies are pure
functions that operate on lists of Well entities and a dict of raw values.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass

from chem_vault.domain.screening_assay.enums import (
    PosControlSignal,
    ReadoutNormalization,
    WellType,
)
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
        pos_control_signal: PosControlSignal = PosControlSignal.HIGH,
    ) -> list[NormalizedValue]:
        """Dispatch to the appropriate normalization strategy.

        ``pos_control_signal`` resolves the convention slip between two wet-lab
        labelings: when ``LOW``, the POS/NEG roles in formula inputs are
        swapped so that the high-signal control always anchors "max activity"
        regardless of how the wells were tagged in the plate template. See
        :class:`PosControlSignal` for the full semantic.
        """
        if normalization == ReadoutNormalization.NONE:
            return []
        if normalization == ReadoutNormalization.PERCENT_INHIBITION:
            return self._percent_inhibition(wells, raw_values, pos_control_signal)
        if normalization == ReadoutNormalization.PERCENT_ACTIVATION:
            return self._percent_activation(wells, raw_values, pos_control_signal)
        if normalization == ReadoutNormalization.PERCENT_CONTROL:
            return self._percent_control(wells, raw_values, pos_control_signal)
        if normalization == ReadoutNormalization.Z_SCORE:
            return self._z_score(wells, raw_values, pos_control_signal)
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
    def _resolve_anchors(
        wells: list[Well],
        raw_values: dict[uuid.UUID, float],
        pos_control_signal: PosControlSignal,
    ) -> tuple[list[float], list[float]]:
        """Return (high_signal_values, low_signal_values).

        Independent of which template label was applied to each control well —
        the caller-supplied ``pos_control_signal`` resolves the role:

        - ``HIGH``: POSITIVE_CONTROL wells anchor the high-signal end (max
          activity); NEGATIVE_CONTROL wells anchor the low-signal end.
        - ``LOW``: roles swap — the lab labels its known-inhibitor wells as
          POSITIVE_CONTROL, but those carry the low signal.
        """
        pos_label = PlateNormalizer._values_for_type(
            wells, raw_values, WellType.POSITIVE_CONTROL
        )
        neg_label = PlateNormalizer._values_for_type(
            wells, raw_values, WellType.NEGATIVE_CONTROL
        )
        if pos_control_signal == PosControlSignal.LOW:
            return neg_label, pos_label
        return pos_label, neg_label

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
        pos_control_signal: PosControlSignal,
    ) -> list[NormalizedValue]:
        """100 * (high_anchor - sample) / (high_anchor - low_anchor).

        Anchors are resolved by ``pos_control_signal``:
            HIGH: high_anchor = POS wells, low_anchor = NEG wells (default)
            LOW:  high_anchor = NEG wells, low_anchor = POS wells (lab's
                  "POS = known inhibitor" convention — POS reads low signal).

        A sample at the high anchor → 0% inhibition; at the low anchor → 100%.
        """
        high_vals, low_vals = self._resolve_anchors(
            wells, raw_values, pos_control_signal
        )
        if not low_vals:
            raise ValidationError(
                "PERCENT_INHIBITION requires at least one low-signal control "
                "well with data (NEGATIVE_CONTROL when pos_control_signal=high; "
                "POSITIVE_CONTROL when pos_control_signal=low)"
            )
        if not high_vals:
            raise ValidationError(
                "PERCENT_INHIBITION requires at least one high-signal control "
                "well with data (POSITIVE_CONTROL when pos_control_signal=high; "
                "NEGATIVE_CONTROL when pos_control_signal=low)"
            )

        high_mean = statistics.mean(high_vals)
        low_mean = statistics.mean(low_vals)

        denominator = high_mean - low_mean
        if denominator == 0.0:
            raise ValidationError(
                "PERCENT_INHIBITION: denominator (high_anchor - low_anchor) is zero"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = 100.0 * (high_mean - sample) / denominator
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
        pos_control_signal: PosControlSignal,
    ) -> list[NormalizedValue]:
        """100 * (sample - low_anchor) / (high_anchor - low_anchor)."""
        high_vals, low_vals = self._resolve_anchors(
            wells, raw_values, pos_control_signal
        )
        if not low_vals:
            raise ValidationError(
                "PERCENT_ACTIVATION requires at least one low-signal control "
                "well with data"
            )
        if not high_vals:
            raise ValidationError(
                "PERCENT_ACTIVATION requires at least one high-signal control "
                "well with data"
            )

        high_mean = statistics.mean(high_vals)
        low_mean = statistics.mean(low_vals)

        denominator = high_mean - low_mean
        if denominator == 0.0:
            raise ValidationError(
                "PERCENT_ACTIVATION: denominator (high_anchor - low_anchor) is zero"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = 100.0 * (sample - low_mean) / denominator
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
        pos_control_signal: PosControlSignal,
    ) -> list[NormalizedValue]:
        """100 * (sample / high_anchor_mean).

        The high-signal control (uninhibited / max-activity) is the natural
        baseline for "% of control activity" — independent of which template
        label the lab assigns to it.
        """
        high_vals, _ = self._resolve_anchors(
            wells, raw_values, pos_control_signal
        )
        if not high_vals:
            raise ValidationError(
                "PERCENT_CONTROL requires at least one high-signal control "
                "well with data"
            )

        high_mean = statistics.mean(high_vals)
        if high_mean == 0.0:
            raise ValidationError(
                "PERCENT_CONTROL: high-signal control mean is zero — cannot divide"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = 100.0 * sample / high_mean
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
        pos_control_signal: PosControlSignal,
    ) -> list[NormalizedValue]:
        """(sample - high_anchor_mean) / high_anchor_stdev.

        Uses the high-signal control's distribution as the reference —
        consistent with PERCENT_CONTROL's choice of baseline.
        """
        high_vals, _ = self._resolve_anchors(
            wells, raw_values, pos_control_signal
        )
        if len(high_vals) < 2:
            raise ValidationError(
                "Z_SCORE requires at least 2 high-signal control wells with data"
            )

        high_mean = statistics.mean(high_vals)
        high_stdev = statistics.stdev(high_vals)

        if high_stdev == 0.0:
            raise ValidationError(
                "Z_SCORE: high-signal control stdev is zero — cannot compute Z-score"
            )

        results: list[NormalizedValue] = []
        for w in self._sample_wells(wells, raw_values):
            sample = raw_values[w.id]
            normalized = (sample - high_mean) / high_stdev
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
