"""Run aggregate root with owned Plate and Well entities."""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any

from cellar.domain.screening_assay.enums import (
    HolderKind,
    PlateFormat,
    RunRelationshipType,
    RunStatus,
    WellType,
)
from cellar.domain.screening_assay.events import (
    FieldChange,
    PositionChange,
    RunApproved,
    RunCompleted,
    RunCreated,
    RunHitCriteriaCleared,
    RunHitCriteriaSet,
    RunInstrumentFileImported,
    RunLocked,
    RunPositionsRelabelled,
    RunRejected,
    RunUnlocked,
)
from cellar.domain.screening_assay.holder import position_label
from cellar.domain.shared.entity import AggregateRoot, Entity
from cellar.domain.shared.errors import (
    ConflictError,
    NotFoundError,
    StaleEditError,
    ValidationError,
)
from cellar.domain.shared.hit_criterion import HitCriterion, validate_hit_criteria
from cellar.domain.shared.value_objects import Barcode

# ---------------------------------------------------------------------------
# Run state machine
# ---------------------------------------------------------------------------

_RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.DRAFT: {RunStatus.IN_PROGRESS},
    RunStatus.IN_PROGRESS: {RunStatus.COMPLETED},
    RunStatus.COMPLETED: {RunStatus.APPROVED, RunStatus.REJECTED},
    RunStatus.APPROVED: set(),  # terminal
    RunStatus.REJECTED: {RunStatus.DRAFT},  # rework
}

_LOCKABLE_STATES = {RunStatus.COMPLETED, RunStatus.APPROVED}

_WELL_LABEL_MAX = 200
_WELL_NOTE_MAX = 1000

# Role/batch/concentration feed calculations: editable only while the run's data can be reset.
_CALCULATION_EDIT_STATES = {RunStatus.DRAFT, RunStatus.IN_PROGRESS}
# Label/note edits on these statuses need a reason.
_REASON_REQUIRED_STATES = {RunStatus.COMPLETED, RunStatus.APPROVED}


def _clean_label(label: str | None) -> str | None:
    label = (label or "").strip() or None
    if label is not None and len(label) > _WELL_LABEL_MAX:
        raise ValidationError(f"Well label must be at most {_WELL_LABEL_MAX} characters")
    return label


def _clean_note(note: str | None) -> str | None:
    note = (note or "").strip() or None
    if note is not None and len(note) > _WELL_NOTE_MAX:
        raise ValidationError(f"Well note must be at most {_WELL_NOTE_MAX} characters")
    return note


def _check_dose(dose: float | None) -> None:
    if dose is not None and not math.isfinite(dose):
        raise ValidationError("Well dose must be a finite number")
    if dose is not None and dose < 0:
        raise ValidationError("Well dose must be >= 0")


@dataclass(frozen=True)
class PositionValues:
    """The editable values of one position (a well)."""

    label: str | None = None
    note: str | None = None
    well_type: WellType = WellType.SAMPLE
    batch_id: uuid.UUID | None = None
    dose: float | None = None


@dataclass(frozen=True)
class PositionEdit:
    """One position's edit: the values the user started from, and the values to store."""

    well_id: uuid.UUID
    expected: PositionValues
    new: PositionValues


def _cleaned(values: PositionValues) -> PositionValues:
    """Normalised and validated exactly as a Well does."""
    _check_dose(values.dose)
    return replace(values, label=_clean_label(values.label), note=_clean_note(values.note))


def _field_changes(
    old: PositionValues, new: PositionValues, batch_names: Mapping[uuid.UUID, str]
) -> tuple[FieldChange, ...]:
    def batch(b: uuid.UUID | None) -> str | None:
        return None if b is None else batch_names.get(b, str(b))

    def dose(d: float | None) -> str | None:
        # repr keeps every digit: an audit row must tell 0.1234567 from 0.1234568.
        return None if d is None else repr(d)

    candidates = (
        ("label", old.label, new.label, old.label, new.label),
        ("note", old.note, new.note, old.note, new.note),
        ("role", old.well_type, new.well_type, old.well_type.value, new.well_type.value),
        ("batch", old.batch_id, new.batch_id, batch(old.batch_id), batch(new.batch_id)),
        ("concentration", old.dose, new.dose, dose(old.dose), dose(new.dose)),
    )
    return tuple(
        FieldChange(name, old_text, new_text)
        for name, old_value, new_value, old_text, new_text in candidates
        if old_value != new_value
    )


# ---------------------------------------------------------------------------
# Owned entities
# ---------------------------------------------------------------------------


class Plate(Entity):
    """A microplate belonging to a run.

    Owned by Run — created and managed only through the aggregate root.

    Invariants:
        - plate_number >= 1
        - holder size is both rows and columns or neither, each >= 1
        - a cassette has one row and no plate format
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        run_id: uuid.UUID,
        plate_number: int,
        barcode: Barcode | None = None,
        format: PlateFormat | None = None,
        plate_map: dict[str, Any] | None = None,
        parent_plate_id: uuid.UUID | None = None,
        template_id: uuid.UUID | None = None,
        registered_plate_id: uuid.UUID | None = None,
        holder_kind: HolderKind = HolderKind.PLATE,
        holder_rows: int | None = None,
        holder_columns: int | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if plate_number < 1:
            raise ValidationError("plate_number must be >= 1")
        if (holder_rows is None) != (holder_columns is None):
            raise ValidationError("holder_rows and holder_columns must be set together")
        if (
            holder_rows is not None
            and holder_columns is not None
            and min(holder_rows, holder_columns) < 1
        ):
            raise ValidationError("holder size must be >= 1")
        if holder_kind is HolderKind.CASSETTE:
            if holder_rows is not None and holder_rows != 1:
                raise ValidationError("A cassette has exactly one row")
            if format is not None:
                raise ValidationError("A cassette has no plate format")

        self.run_id = run_id
        self.plate_number = plate_number
        self.barcode = barcode
        self.format = format
        self.plate_map = plate_map
        self.parent_plate_id = parent_plate_id
        self.template_id = template_id
        # Optional link to the physical inventory plate (RegisteredPlate) this
        # run plate was run on. Null is normal — nothing depends on it.
        self.registered_plate_id = registered_plate_id
        self.holder_kind = holder_kind
        self.holder_rows = holder_rows
        self.holder_columns = holder_columns


class Well(Entity):
    """A single well on a plate.

    Owned by Run — created and managed only through the aggregate root.

    Invariants:
        - row: 1-2 uppercase characters
        - column >= 1
        - dose, when given, is finite and >= 0
        - label, when given, is trimmed and at most 200 characters
        - note, when given, is trimmed and at most 1000 characters
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        plate_id: uuid.UUID,
        row: str,
        column: int,
        well_type: WellType = WellType.SAMPLE,
        batch_id: uuid.UUID | None = None,
        dose: float | None = None,
        label: str | None = None,
        note: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        label = _clean_label(label)
        note = _clean_note(note)

        # Normalize row to uppercase
        row = row.upper()
        if not row or len(row) > 2 or not row.isalpha():
            raise ValidationError("Well row must be 1-2 alphabetic characters")
        if column < 1:
            raise ValidationError("Well column must be >= 1")
        _check_dose(dose)

        self.plate_id = plate_id
        self.row = row
        self.column = column
        self.well_type = well_type
        self.batch_id = batch_id
        # Dose value only — unit is the owning protocol's dose_unit. Not
        # carried per-well to avoid duplication and inconsistency.
        self.dose = dose
        # Free-text identifier of what was measured here (e.g. a sample name).
        self.label = label
        # Free-text observation made at the bench about this sample in this run.
        self.note = note

    @property
    def values(self) -> PositionValues:
        """The fields a user can edit after import."""
        return PositionValues(
            label=self.label,
            note=self.note,
            well_type=self.well_type,
            batch_id=self.batch_id,
            dose=self.dose,
        )


# ---------------------------------------------------------------------------
# Run aggregate root
# ---------------------------------------------------------------------------


class Run(AggregateRoot):
    """An execution of a protocol — the central screening experiment record.

    Invariants:
        - parent_run_id and run_relationship_type must both be set or both null
        - Status transitions follow the state machine
        - Locked runs cannot be modified (plates, QC metrics)
        - Only completed or approved runs can be locked

    State machine:
        draft -[start]-> in_progress -[complete]-> completed
            -[approve]-> approved (terminal)
            -[reject]-> rejected -[rework]-> draft
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        run_date: date,
        operator: uuid.UUID,
        performed_at_org_id: uuid.UUID | None = None,
        status: RunStatus = RunStatus.DRAFT,
        parent_run_id: uuid.UUID | None = None,
        run_relationship_type: RunRelationshipType | None = None,
        plate_format: PlateFormat | None = None,
        plate_template_id: uuid.UUID | None = None,
        conditions: dict[str, Any] | None = None,
        qc_metrics: dict[str, Any] | None = None,
        is_locked: bool = False,
        locked_at: datetime | None = None,
        locked_by: uuid.UUID | None = None,
        lock_reason: str | None = None,
        notes: str | None = None,
        eln_entry_id: uuid.UUID | None = None,
        hit_criteria: list[HitCriterion] | None = None,
        hit_criteria_set_by: uuid.UUID | None = None,
        hit_criteria_set_at: datetime | None = None,
        plates: list[Plate] | None = None,
        wells: list[Well] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        # Parent run consistency: both or neither
        has_parent = parent_run_id is not None
        has_relationship = run_relationship_type is not None
        if has_parent != has_relationship:
            raise ValidationError(
                "parent_run_id and run_relationship_type must both be set or both null"
            )

        self.workspace_id = workspace_id
        self.protocol_id = protocol_id
        self.run_date = run_date
        self.operator = operator
        self.performed_at_org_id = performed_at_org_id
        self.status = status
        self.parent_run_id = parent_run_id
        self.run_relationship_type = run_relationship_type
        self.plate_format = plate_format
        self.plate_template_id = plate_template_id
        self.conditions = conditions
        self.qc_metrics = qc_metrics
        self.is_locked = is_locked
        self.locked_at = locked_at
        self.locked_by = locked_by
        self.lock_reason = lock_reason
        self.notes = notes
        self.eln_entry_id = eln_entry_id
        # Per-run hit criteria — an attributable analytical decision, distinct
        # from the protocol's recommended criteria (the SOP suggestion). None
        # means "unset" (show the recommendation); a list (possibly empty,
        # meaning "show all, on purpose") means a decision was recorded. The
        # provenance pair below is non-null iff hit_criteria is non-null.
        self.hit_criteria: list[HitCriterion] | None = hit_criteria
        self.hit_criteria_set_by = hit_criteria_set_by
        self.hit_criteria_set_at = hit_criteria_set_at
        self.plates: list[Plate] = plates or []
        self.wells: list[Well] = wells or []

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _guard_transition(self, target: RunStatus) -> None:
        allowed = _RUN_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ConflictError(f"Cannot transition run from '{self.status}' to '{target}'")

    def _guard_not_locked(self) -> None:
        if self.is_locked:
            raise ConflictError("Cannot modify a locked run — unlock it first")

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        run_date: date,
        operator: uuid.UUID,
        performed_at_org_id: uuid.UUID | None = None,
        parent_run_id: uuid.UUID | None = None,
        run_relationship_type: RunRelationshipType | None = None,
        plate_format: PlateFormat | None = None,
        plate_template_id: uuid.UUID | None = None,
        conditions: dict[str, Any] | None = None,
        notes: str | None = None,
        eln_entry_id: uuid.UUID | None = None,
    ) -> Run:
        run = cls(
            workspace_id=workspace_id,
            protocol_id=protocol_id,
            run_date=run_date,
            operator=operator,
            performed_at_org_id=performed_at_org_id,
            parent_run_id=parent_run_id,
            run_relationship_type=run_relationship_type,
            plate_format=plate_format,
            plate_template_id=plate_template_id,
            conditions=conditions,
            notes=notes,
            eln_entry_id=eln_entry_id,
        )
        run.register_event(
            RunCreated(
                aggregate_id=run.id,
                aggregate_type="Run",
                workspace_id=workspace_id,
                protocol_id=protocol_id,
                operator=operator,
            )
        )
        return run

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Move run from draft to in_progress."""
        self._guard_transition(RunStatus.IN_PROGRESS)
        self.status = RunStatus.IN_PROGRESS
        self.updated_at = datetime.now(UTC)

    def complete(self, *, plate_count: int, data_point_count: int) -> None:
        """Mark run as completed with summary metrics."""
        self._guard_transition(RunStatus.COMPLETED)
        self.status = RunStatus.COMPLETED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            RunCompleted(
                aggregate_id=self.id,
                aggregate_type="Run",
                workspace_id=self.workspace_id,
                plate_count=plate_count,
                data_point_count=data_point_count,
            )
        )

    def approve(self, *, approved_by: uuid.UUID) -> None:
        """Approve a completed run."""
        self._guard_transition(RunStatus.APPROVED)
        self.status = RunStatus.APPROVED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            RunApproved(
                aggregate_id=self.id,
                aggregate_type="Run",
                workspace_id=self.workspace_id,
                approved_by=approved_by,
            )
        )

    def reject(self, *, rejected_by: uuid.UUID, reason: str) -> None:
        """Reject a completed run. Reason is required."""
        if not reason or not reason.strip():
            raise ValidationError("Rejection reason is required")
        self._guard_transition(RunStatus.REJECTED)
        self.status = RunStatus.REJECTED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            RunRejected(
                aggregate_id=self.id,
                aggregate_type="Run",
                workspace_id=self.workspace_id,
                rejected_by=rejected_by,
                reason=reason.strip(),
            )
        )

    def rework(self) -> None:
        """Send a rejected run back to draft for rework."""
        self._guard_transition(RunStatus.DRAFT)
        self.status = RunStatus.DRAFT
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Data modification (lock-guarded)
    # ------------------------------------------------------------------

    def update(self, **fields: Any) -> None:
        """Partial update of mutable fields. Blocked when run is locked.

        Supported fields: qc_metrics, notes, conditions.
        """
        self._guard_not_locked()
        for key, value in fields.items():
            if key == "qc_metrics":
                self.qc_metrics = value
            elif key == "notes":
                self.notes = value
            elif key == "conditions":
                self.conditions = value
            else:
                raise ValidationError(f"Cannot update field '{key}' on Run")
        self.updated_at = datetime.now(UTC)

    def record_qc_metrics(self, metrics: dict[str, Any]) -> None:
        """Update QC metrics. Blocked when run is locked."""
        self._guard_not_locked()
        self.qc_metrics = metrics
        self.updated_at = datetime.now(UTC)

    def add_plate(self, plate: Plate) -> None:
        """Add a plate to this run. Blocked when run is locked."""
        self._guard_not_locked()
        plate.run_id = self.id
        self.plates.append(plate)
        # Sync plate's wells into the flat wells list so _update_model can find them
        for well in getattr(plate, "wells", []):
            well.plate_id = plate.id
            self.wells.append(well)
        self.updated_at = datetime.now(UTC)

    def link_plate(self, plate_id: uuid.UUID, registered_plate_id: uuid.UUID | None) -> None:
        """Point a run plate at the physical inventory plate it was run on (or clear it).

        Optional by design — a run plate without a link is normal. ``None``
        unlinks. Blocked when run is locked.
        """
        self._guard_not_locked()
        plate = next((p for p in self.plates if p.id == plate_id), None)
        if plate is None:
            raise NotFoundError("Plate", str(plate_id))
        plate.registered_plate_id = registered_plate_id
        self.updated_at = datetime.now(UTC)

    def clear_plate_format(self) -> None:
        """Forget the run's plate format, for a run whose holder is not a plate.

        Blocked when the run is locked.
        """
        self._guard_not_locked()
        self.plate_format = None
        self.updated_at = datetime.now(UTC)

    def record_instrument_import(
        self,
        *,
        reader: str,
        file_name: str,
        positions: int,
        curves: int,
        readout_values: int,
    ) -> None:
        """Record that an instrument file was imported into this run (blocked when locked)."""
        self._guard_not_locked()
        self.register_event(
            RunInstrumentFileImported(
                workspace_id=self.workspace_id,
                aggregate_id=self.id,
                aggregate_type="Run",
                reader=reader,
                file_name=file_name,
                positions=positions,
                curves=curves,
                readout_values=readout_values,
            )
        )

    def check_position_edits(self, edits: Sequence[PositionEdit]) -> None:
        """The checks ``relabel_positions`` makes before it compares anything: the run is
        not locked, each position is on the run and given once, its values are valid, and
        nothing changed since the user opened it (a conflict naming the positions).
        Changes nothing."""
        self._checked_position_edits(edits)

    def relabel_positions(
        self,
        edits: Sequence[PositionEdit],
        *,
        reason: str | None = None,
        batch_names: Mapping[uuid.UUID, str] | None = None,
    ) -> tuple[PositionChange, ...]:
        """Edit positions' label, note, role, batch and concentration after import.

        Every check runs before anything is changed. An edit whose ``expected`` no
        longer matches what is stored is a conflict (someone else saved first). Label
        and note can be edited in any unlocked status, with a reason on a completed or
        approved run; role, batch and concentration only while draft or in progress.
        Returns the changes; no change registers nothing.
        """
        checked = self._checked_position_edits(edits)

        names = batch_names or {}
        changed: list[tuple[Well, PositionValues, PositionChange]] = []
        for well, label, _, new in checked:
            fields = _field_changes(well.values, new, names)
            if fields:
                changed.append((well, new, PositionChange(well.id, label, fields)))
        if not changed:
            return ()

        if (
            any(change.touches_calculation for _, _, change in changed)
            and self.status not in _CALCULATION_EDIT_STATES
        ):
            raise ConflictError(
                "Role, batch and concentration can be changed only while the run is "
                "draft or in progress"
            )
        reason = (reason or "").strip() or None
        if self.status in _REASON_REQUIRED_STATES and reason is None:
            raise ValidationError("A reason is required to edit a completed or approved run")

        for well, new, _ in changed:
            well.label = new.label
            well.note = new.note
            well.well_type = new.well_type
            well.batch_id = new.batch_id
            well.dose = new.dose
        self.updated_at = datetime.now(UTC)
        changes = tuple(change for _, _, change in changed)
        self.register_event(
            RunPositionsRelabelled(
                workspace_id=self.workspace_id,
                aggregate_id=self.id,
                aggregate_type="Run",
                positions=changes,
                reason=reason,
            )
        )
        return changes

    def _checked_position_edits(
        self, edits: Sequence[PositionEdit]
    ) -> list[tuple[Well, str, PositionValues, PositionValues]]:
        self._guard_not_locked()

        wells = {w.id: w for w in self.wells}
        plates = {p.id: p for p in self.plates}
        checked: list[tuple[Well, str, PositionValues, PositionValues]] = []
        seen: set[uuid.UUID] = set()
        for edit in edits:
            well = wells.get(edit.well_id)
            if well is None:
                raise ValidationError(f"Position '{edit.well_id}' is not on this run")
            if edit.well_id in seen:
                raise ValidationError(f"Position '{edit.well_id}' is given more than once")
            seen.add(edit.well_id)
            plate = plates[well.plate_id]
            label = position_label(plate.holder_kind, well.row, well.column)
            try:
                expected, new = _cleaned(edit.expected), _cleaned(edit.new)
            except ValidationError as exc:
                raise ValidationError(f"{label}: {exc.message}") from exc
            checked.append((well, label, expected, new))

        stale = [label for well, label, expected, _ in checked if expected != well.values]
        if stale:
            raise StaleEditError(
                f"Changed by someone else since you opened them: {', '.join(stale)}. "
                "Reload and try again."
            )
        return checked

    def reset_data(
        self,
        *,
        readouts_deleted: int,
        curves_deleted: int,
        measured_curves_deleted: int = 0,
    ) -> None:
        """Wipe plates, wells, and QC metrics on this run.

        Cascades plates → wells via the FK relationship at persistence
        time. Readouts and curves are owned by separate repositories;
        their deletion happens in the use case before this method is
        called, and the counts are passed in for the emitted event.

        Blocked on locked runs. Run row, run metadata, and attachments
        are preserved.
        """
        from cellar.domain.screening_assay.events import RunDataReset

        self._guard_not_locked()
        plates_deleted = len(self.plates)
        wells_deleted = len(self.wells)
        self.plates = []
        self.wells = []
        self.qc_metrics = {}
        self.updated_at = datetime.now(UTC)
        self.register_event(
            RunDataReset(
                workspace_id=self.workspace_id,
                aggregate_id=self.id,
                aggregate_type="Run",
                plates_deleted=plates_deleted,
                wells_deleted=wells_deleted,
                readouts_deleted=readouts_deleted,
                curves_deleted=curves_deleted,
                measured_curves_deleted=measured_curves_deleted,
            )
        )

    # ------------------------------------------------------------------
    # Locking
    # ------------------------------------------------------------------

    def lock(self, *, locked_by: uuid.UUID, reason: str) -> None:
        """Lock the run to prevent data modifications.

        Only completed or approved runs can be locked.
        """
        if not reason or not reason.strip():
            raise ValidationError("Lock reason is required")
        if self.is_locked:
            raise ConflictError("Run is already locked")
        if self.status not in _LOCKABLE_STATES:
            raise ConflictError(
                f"Cannot lock run in '{self.status}' status — "
                "only completed or approved runs can be locked"
            )

        self.is_locked = True
        self.locked_at = datetime.now(UTC)
        self.locked_by = locked_by
        self.lock_reason = reason.strip()
        self.updated_at = datetime.now(UTC)
        self.register_event(
            RunLocked(
                aggregate_id=self.id,
                aggregate_type="Run",
                workspace_id=self.workspace_id,
                locked_by=locked_by,
                lock_reason=reason.strip(),
            )
        )

    def unlock(self, *, unlocked_by: uuid.UUID, reason: str) -> None:
        """Unlock a previously locked run."""
        if not reason or not reason.strip():
            raise ValidationError("Unlock reason is required")
        if not self.is_locked:
            raise ConflictError("Run is not locked")

        self.is_locked = False
        self.locked_at = None
        self.locked_by = None
        self.lock_reason = None
        self.updated_at = datetime.now(UTC)
        self.register_event(
            RunUnlocked(
                aggregate_id=self.id,
                aggregate_type="Run",
                workspace_id=self.workspace_id,
                unlocked_by=unlocked_by,
                reason=reason.strip(),
            )
        )

    # ------------------------------------------------------------------
    # Hit criteria (per-run, attributable analytical decision)
    # ------------------------------------------------------------------

    def set_hit_criteria(self, criteria: list[HitCriterion], *, set_by: uuid.UUID) -> None:
        """Record this run's hit criteria — an attributable per-run decision.

        An empty list is a valid, recorded decision meaning "no threshold —
        show all compounds". ``None`` is never stored through this method;
        reverting to "unset" (so the protocol recommendation is shown again)
        goes through :meth:`clear_hit_criteria`.

        Frozen on locked runs — the hit threshold is part of the run's
        finalized analytical record, like its dose-response curves.
        """
        self._guard_not_locked()
        validate_hit_criteria(criteria)
        self.hit_criteria = list(criteria)
        self.hit_criteria_set_by = set_by
        self.hit_criteria_set_at = datetime.now(UTC)
        self.updated_at = self.hit_criteria_set_at
        self.register_event(
            RunHitCriteriaSet(
                aggregate_id=self.id,
                aggregate_type="Run",
                workspace_id=self.workspace_id,
                set_by=set_by,
                rule_count=len(criteria),
            )
        )

    def clear_hit_criteria(self, *, cleared_by: uuid.UUID) -> None:
        """Clear this run's hit criteria, reverting to "unset".

        Provenance is nulled atomically with the criteria, restoring the
        invariant that the set_by/set_at pair is non-null iff hit_criteria is.
        Frozen on locked runs.
        """
        self._guard_not_locked()
        self.hit_criteria = None
        self.hit_criteria_set_by = None
        self.hit_criteria_set_at = None
        self.updated_at = datetime.now(UTC)
        self.register_event(
            RunHitCriteriaCleared(
                aggregate_id=self.id,
                aggregate_type="Run",
                workspace_id=self.workspace_id,
                cleared_by=cleared_by,
            )
        )
