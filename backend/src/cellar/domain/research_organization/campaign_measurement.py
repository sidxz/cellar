"""CampaignMeasurement — one frozen cell owned by a CampaignResult.

The atomic unit of the snapshot: (compound, channel) -> (value, qualifier,
unit, source FKs, protocol snapshot fields). At close, every auto-resolved
cell is locked in. Manual edits flip is_manual_override so the cell is
preserved through subsequent recomputes. Hit/miss verdicts are computed at
read time by ``stage_evaluation`` against ``CampaignStage`` criteria — no
per-cell hit call is stored here (see the campaign-hit-stages spec §5).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from cellar.domain.research_organization.enums import (
    MeasurementBasis,
    QcVerdict,
    UnresolvedReason,
    ValueQualifier,
)
from cellar.domain.research_organization.measurement_facts import Concentration
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.units import canonical_unit

QC_NOTE_MAX_LENGTH = 2000

_UNTESTED_QUALIFIERS = frozenset({ValueQualifier.ND, ValueQualifier.EXCLUDED})


class QcApplyOutcome(StrEnum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    KEPT = "kept"
    NO_RESULT = "no_result"


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=1e-9)


@dataclass
class CampaignMeasurement:
    result_id: uuid.UUID
    channel_id: uuid.UUID
    value: float | None
    value_qualifier: ValueQualifier
    unit: str
    protocol_name_snapshot: str
    protocol_version_snapshot: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    is_manual_override: bool = False
    source_run_id: uuid.UUID | None = None
    source_curve_id: uuid.UUID | None = None
    source_readout_id: uuid.UUID | None = None
    run_date_snapshot: date | None = None
    # Migration 029 — report-grade audit + snapshot fields
    override_reason: str | None = None
    test_concentration_value: float | None = None
    test_concentration_unit: str | None = None
    replicate_count: int | None = None
    contributing_run_ids: list[uuid.UUID] | None = None
    # Migration 031 — frozen copy of the underlying dose-response curve so the
    # campaign's drawing is reproducible from the row alone (no live FK lookup
    # against `dose_response_curves`). Only populated for source_kind=
    # dose_response_curve channels; ReadoutData cells leave this NULL.
    # Shape:
    #   {"fitted_value", "top", "bottom", "hill_slope", "r_squared",
    #    "curve_class", "raw_data": [{"x", "y"}, ...],
    #    "excluded_points": [{"x", "y"}, ...] | null}
    curve_snapshot: dict[str, Any] | None = None
    batch_ids: list[uuid.UUID] | None = None
    basis: MeasurementBasis | None = None
    concentration_series: bool = False
    unresolved_reason: UnresolvedReason | None = None
    #: A person's QC call on this value; None = not tested. Nothing automatic sets it.
    qc_verdict: QcVerdict | None = None
    qc_verdict_by: uuid.UUID | None = None
    qc_verdict_at: datetime | None = None
    qc_verdict_note: str | None = None
    #: Single-concentration columns: the distinct known doses this compound was measured
    #: at (series runs and not-recorded excluded), whatever the cell resolved to.
    concentrations_found: list[Concentration] | None = None

    def __post_init__(self) -> None:
        numeric_qualifiers = {
            ValueQualifier.EQ,
            ValueQualifier.LT,
            ValueQualifier.GT,
        }
        if self.value_qualifier in numeric_qualifiers and self.value is None:
            raise ValidationError(
                f"qualifier {self.value_qualifier.value!r} requires a numeric value"
            )
        if self.value_qualifier in {ValueQualifier.ND, ValueQualifier.EXCLUDED}:
            # ND/excluded are placeholders — value must be None and unit may be empty
            self.value = None
            self.unit = (self.unit or "").strip()
            return
        if not self.unit or not self.unit.strip():
            raise ValidationError(
                "CampaignMeasurement.unit must not be empty (use qualifier=nd for missing data)"
            )
        self.unit = self.unit.strip()

    def mark_manual_override(self, reason: str | None = None) -> None:
        self.is_manual_override = True
        if reason is not None:
            self.override_reason = reason

    @property
    def is_tested_nd(self) -> bool:
        """True for an ND cell that came off a curve the assay actually produced.

        The compound WAS tested; the fit simply yielded no readable value (an
        Inactive classification, or no intercept of the channel's kind). That is a
        real negative result, not a gap in the data — owner's rule, 2026-09-13:
        *"'ND' is not untested, it is miss because we have raw values but IC50
        cannot be determined from curve."*

        An ND with no curve behind it (nothing resolved for the cell at all) and
        EXCLUDED stay untested.

        ponytail: direction-blind. Right for a potency cut (`IC50 lt 10`), wrong
        for a "no response is good" cut (a cytotoxicity `CC50 gte 50`), where an
        inactive compound ought to pass. No such stage exists yet; give
        StageCriterion a per-criterion knob when one does.
        """
        return self.value_qualifier == ValueQualifier.ND and (
            self.source_curve_id is not None or self.curve_snapshot is not None
        )

    @property
    def holds_result(self) -> bool:
        """A value or a tested ND: the cells a person can put a QC verdict on."""
        return self.is_tested_nd or (
            self.value is not None and self.value_qualifier not in _UNTESTED_QUALIFIERS
        )

    def apply_qc_verdict(
        self,
        verdict: QcVerdict | None,
        *,
        by: uuid.UUID,
        at: datetime,
        note: str | None,
        overwrite: bool,
    ) -> QcApplyOutcome:
        note = (note or "").strip() or None
        if note is not None and verdict is None:
            raise ValidationError("a QC note needs a verdict")
        if note is not None and len(note) > QC_NOTE_MAX_LENGTH:
            raise ValidationError(f"QC note must be at most {QC_NOTE_MAX_LENGTH} characters")
        if not self.holds_result:
            return QcApplyOutcome.NO_RESULT
        if verdict is None:
            if self.qc_verdict is None:
                return QcApplyOutcome.UNCHANGED
        elif self.qc_verdict == verdict:
            if not (overwrite and note != self.qc_verdict_note):
                return QcApplyOutcome.UNCHANGED
        elif self.qc_verdict is not None and not overwrite:
            return QcApplyOutcome.KEPT
        self.qc_verdict = verdict
        self.qc_verdict_by = by if verdict else None
        self.qc_verdict_at = at if verdict else None
        self.qc_verdict_note = note
        return QcApplyOutcome.CHANGED

    def carry_qc_verdict_from(self, old: CampaignMeasurement) -> bool:
        """Take ``old``'s verdict when this cell is the same reading; else stay not tested."""
        if old.qc_verdict is None or not self._same_reading_as(old):
            return False
        self.qc_verdict = old.qc_verdict
        self.qc_verdict_by = old.qc_verdict_by
        self.qc_verdict_at = old.qc_verdict_at
        self.qc_verdict_note = old.qc_verdict_note
        return True

    def _same_reading_as(self, old: CampaignMeasurement) -> bool:
        if self.value_qualifier != old.value_qualifier or not _close(self.value, old.value):
            return False
        if self.value_qualifier not in _UNTESTED_QUALIFIERS and canonical_unit(
            self.unit
        ) != canonical_unit(old.unit):
            return False
        return (
            _close(self.test_concentration_value, old.test_concentration_value)
            and canonical_unit(self.test_concentration_unit)
            == canonical_unit(old.test_concentration_unit)
            and self.concentration_series == old.concentration_series
            and set(self.contributing_run_ids or []) == set(old.contributing_run_ids or [])
        )
