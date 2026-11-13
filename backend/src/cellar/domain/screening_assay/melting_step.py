"""MeltingStep entity: one Tm on one position's trace, reviewable by a scientist."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from cellar.domain.screening_assay.measured_curve import ReportedPoint
from cellar.domain.screening_assay.melt_window import STEP_KIND
from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError

REASON_MAX = 500


class MeltingStepSource(StrEnum):
    INSTRUMENT = "instrument"
    MANUAL = "manual"


class MeltingStepStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def _fmt(value: float) -> str:
    return f"{value:.15g}"


def _clean_reason(reason: str | None) -> str | None:
    reason = (reason or "").strip() or None
    if reason is not None and len(reason) > REASON_MAX:
        raise ValidationError(f"The reason must be at most {REASON_MAX} characters")
    return reason


def _check_value(value: float, x_range: tuple[float, float]) -> None:
    lo, hi = x_range
    if not (math.isfinite(value) and lo <= value <= hi):
        raise ValidationError(f"The value must lie within the trace, {lo:g} to {hi:g} °C")


class MeltingStep(Entity):
    """A melting step (Tm) on one position's trace for one channel.

    Instrument steps keep the value the instrument reported; a correction changes
    ``value`` only. Not an AggregateRoot (no events), but versioned so two people
    editing the same step cannot overwrite each other.

    Invariants:
        - value is finite
        - an instrument step has an instrument value and label; a manual step has neither
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        well_id: uuid.UUID,
        channel_key: str,
        source: MeltingStepSource,
        value: float,
        instrument_value: float | None = None,
        instrument_label: str | None = None,
        status: MeltingStepStatus = MeltingStepStatus.UNREVIEWED,
        reason: str | None = None,
        changed_by: uuid.UUID | None = None,
        changed_at: datetime | None = None,
        version: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        source = MeltingStepSource(source)
        if not math.isfinite(value):
            raise ValidationError("A melting step value must be a finite number")
        if source is MeltingStepSource.INSTRUMENT:
            if instrument_value is None or instrument_label is None:
                raise ValidationError("An instrument melting step needs its instrument value")
            if not math.isfinite(instrument_value):
                raise ValidationError("A melting step value must be a finite number")
        elif instrument_value is not None or instrument_label is not None:
            raise ValidationError("A manual melting step has no instrument value")

        self.workspace_id = workspace_id
        self.run_id = run_id
        self.well_id = well_id
        self.channel_key = channel_key
        self.source = source
        self.value = value
        self.instrument_value = instrument_value
        self.instrument_label = instrument_label
        self.status = MeltingStepStatus(status)
        self.reason = reason
        self.changed_by = changed_by
        self.changed_at = changed_at
        self.version = version

    @classmethod
    def from_reported(
        cls,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        well_id: uuid.UUID,
        channel_key: str,
        point: ReportedPoint,
    ) -> MeltingStep:
        if point.kind != STEP_KIND:
            raise ValidationError(f"'{point.label}' is not a melting step")
        return cls(
            workspace_id=workspace_id,
            run_id=run_id,
            well_id=well_id,
            channel_key=channel_key,
            source=MeltingStepSource.INSTRUMENT,
            value=point.value,
            instrument_value=point.value,
            instrument_label=point.label,
        )

    @classmethod
    def manual(
        cls,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        well_id: uuid.UUID,
        channel_key: str,
        value: float,
        x_range: tuple[float, float],
        reason: str | None,
        by: uuid.UUID,
    ) -> MeltingStep:
        _check_value(value, x_range)
        return cls(
            workspace_id=workspace_id,
            run_id=run_id,
            well_id=well_id,
            channel_key=channel_key,
            source=MeltingStepSource.MANUAL,
            value=value,
            reason=_clean_reason(reason),
            changed_by=by,
            changed_at=datetime.now(UTC),
        )

    @property
    def counts(self) -> bool:
        """Unreviewed and accepted steps feed calculations; rejected ones do not."""
        return self.status is not MeltingStepStatus.REJECTED

    def review(
        self,
        *,
        status: MeltingStepStatus,
        value: float,
        reason: str | None,
        x_range: tuple[float, float],
        by: uuid.UUID,
    ) -> list[tuple[str, str | None, str | None]]:
        """Set status, value and reason; returns (field, old, new) for each change."""
        status = MeltingStepStatus(status)
        reason = _clean_reason(reason)
        _check_value(value, x_range)
        if status is MeltingStepStatus.REJECTED and reason is None:
            raise ValidationError("A reason is required to reject a melting step")
        baseline = self.instrument_value if self.instrument_value is not None else self.value
        if value != baseline and reason is None:
            raise ValidationError("A reason is required to change the value")

        changes: list[tuple[str, str | None, str | None]] = []
        if status is not self.status:
            changes.append(("status", self.status.value, status.value))
        if value != self.value:
            changes.append(("value", _fmt(self.value), _fmt(value)))
        if reason != self.reason:
            changes.append(("reason", self.reason, reason))
        if not changes:
            return []

        now = datetime.now(UTC)
        self.status, self.value, self.reason = status, value, reason
        self.changed_by, self.changed_at, self.updated_at = by, now, now
        self.version += 1
        return changes
