"""MeltingStep entity: one Tm on one position's trace, reviewable by a scientist."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from cellar.domain.screening_assay.measured_curve import ReportedPoint
from cellar.domain.screening_assay.melt_window import STEP_KIND, WINDOW_NAME_MAX, StepFact
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


def _clean_window(window: str | None) -> str | None:
    if window is None:
        return None
    window = window.strip()
    if not 1 <= len(window) <= WINDOW_NAME_MAX:
        raise ValidationError(f"Temperature window name must be 1 to {WINDOW_NAME_MAX} characters")
    return window


def _check_value(value: float, x_range: tuple[float, float]) -> None:
    lo, hi = x_range
    if not (math.isfinite(value) and lo <= value <= hi):
        raise ValidationError(f"The value must lie within the trace, {lo:g} to {hi:g} °C")


class MeltingStep(Entity):
    """A melting step (Tm) on one position's trace for one channel.

    Instrument steps keep the value the instrument reported; a correction changes
    ``value`` only. Not an AggregateRoot (no events), but versioned so two people
    editing the same step cannot overwrite each other.

    A step can be assigned to a temperature window: it then gives the position's
    Tm in that window whatever its value. The assignment has its own reason,
    person and time, apart from the review's.

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
        assigned_window: str | None = None,
        assignment_reason: str | None = None,
        assigned_by: uuid.UUID | None = None,
        assigned_at: datetime | None = None,
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
        self.assigned_window = assigned_window
        self.assignment_reason = assignment_reason
        self.assigned_by = assigned_by
        self.assigned_at = assigned_at
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
        assigned_window: str | None = None,
    ) -> MeltingStep:
        """A step placed by hand; when assigned in the same save, the one reason serves both."""
        _check_value(value, x_range)
        reason = _clean_reason(reason)
        assigned_window = _clean_window(assigned_window)
        now = datetime.now(UTC)
        return cls(
            workspace_id=workspace_id,
            run_id=run_id,
            well_id=well_id,
            channel_key=channel_key,
            source=MeltingStepSource.MANUAL,
            value=value,
            # Placed by the scientist, so already reviewed, like a corrected step.
            status=MeltingStepStatus.ACCEPTED,
            reason=reason,
            changed_by=by,
            changed_at=now,
            assigned_window=assigned_window,
            assignment_reason=reason if assigned_window else None,
            assigned_by=by if assigned_window else None,
            assigned_at=now if assigned_window else None,
        )

    @property
    def counts(self) -> bool:
        """Unreviewed and accepted steps feed calculations; rejected ones do not."""
        return self.status is not MeltingStepStatus.REJECTED

    @property
    def fact(self) -> StepFact:
        """This step as the window naming rule sees it."""
        return StepFact(
            id=self.id,
            well_id=self.well_id,
            channel_key=self.channel_key,
            value=self.value,
            counts=self.counts,
            assigned_window=self.assigned_window,
        )

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

    def accept(self, *, by: uuid.UUID) -> list[tuple[str, str | None, str | None]]:
        """Mark an unreviewed step accepted, its value and reason untouched; returns
        (field, old, new).

        A step already accepted, or rejected, is left exactly as it is: restoring a
        rejected step is a review of that step.
        """
        if self.status is not MeltingStepStatus.UNREVIEWED:
            return []
        # The value does not change, so there is no trace to check it against.
        return self.review(
            status=MeltingStepStatus.ACCEPTED,
            value=self.value,
            reason=self.reason,
            x_range=(self.value, self.value),
            by=by,
        )

    def assign(
        self, *, window: str | None, reason: str | None, by: uuid.UUID
    ) -> list[tuple[str, str | None, str | None]]:
        """Assign to a window, or clear with ``window=None``; returns (field, old, new).

        Assigning marks the step accepted (the scientist judged it), which restores
        a rejected one. Clearing leaves the status alone.
        """
        window = _clean_window(window)
        # A cleared assignment keeps nothing; the reason for clearing goes to the audit trail.
        reason = _clean_reason(reason) if window else None
        status = MeltingStepStatus.ACCEPTED if window else self.status

        changes: list[tuple[str, str | None, str | None]] = []
        if window != self.assigned_window:
            changes.append(("assigned_window", self.assigned_window, window))
        if reason != self.assignment_reason:
            changes.append(("assignment_reason", self.assignment_reason, reason))
        if status is not self.status:
            changes.append(("status", self.status.value, status.value))
        if not changes:
            return []

        now = datetime.now(UTC)
        self.assigned_window, self.assignment_reason, self.status = window, reason, status
        self.assigned_by, self.assigned_at = (by, now) if window else (None, None)
        self.updated_at = now
        self.version += 1
        return changes
