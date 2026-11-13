"""Tests for Run aggregate root, Plate, and Well entities."""

import uuid
from dataclasses import replace
from datetime import date

import pytest

from cellar.domain.screening_assay.enums import (
    HolderKind,
    PlateFormat,
    RunRelationshipType,
    RunStatus,
    WellType,
)
from cellar.domain.screening_assay.events import (
    FieldChange,
    RunApproved,
    RunCompleted,
    RunCreated,
    RunDataReset,
    RunHitCriteriaCleared,
    RunHitCriteriaSet,
    RunInstrumentFileImported,
    RunLocked,
    RunPositionsRelabelled,
    RunRejected,
    RunUnlocked,
)
from cellar.domain.screening_assay.holder import position_label
from cellar.domain.screening_assay.run import Plate, PositionEdit, PositionValues, Run, Well
from cellar.domain.shared.errors import (
    ConflictError,
    NotFoundError,
    StaleEditError,
    ValidationError,
)
from cellar.domain.shared.hit_criterion import HitCriterion
from cellar.domain.shared.value_objects import Barcode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def protocol_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def operator_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    workspace_id: uuid.UUID,
    protocol_id: uuid.UUID,
    operator_id: uuid.UUID,
    **kwargs,
) -> Run:
    defaults = dict(
        workspace_id=workspace_id,
        protocol_id=protocol_id,
        run_date=date(2025, 6, 15),
        operator=operator_id,
    )
    defaults.update(kwargs)
    return Run.create(**defaults)


def _make_plate(run_id: uuid.UUID, **kwargs) -> Plate:
    defaults = dict(
        run_id=run_id,
        plate_number=1,
    )
    defaults.update(kwargs)
    return Plate(**defaults)


def _make_well(plate_id: uuid.UUID, **kwargs) -> Well:
    defaults = dict(
        plate_id=plate_id,
        row="A",
        column=1,
    )
    defaults.update(kwargs)
    return Well(**defaults)


# ---------------------------------------------------------------------------
# TestRunCreation
# ---------------------------------------------------------------------------


class TestRunCreation:
    def test_create_sets_all_fields(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        org_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        run = _make_run(
            workspace_id,
            protocol_id,
            operator_id,
            performed_at_org_id=org_id,
            parent_run_id=parent_id,
            run_relationship_type=RunRelationshipType.REPEAT_OF,
            plate_format=PlateFormat.F384,
            conditions={"temperature": "37C"},
            notes="Test run",
        )

        assert run.workspace_id == workspace_id
        assert run.protocol_id == protocol_id
        assert run.run_date == date(2025, 6, 15)
        assert run.operator == operator_id
        assert run.performed_at_org_id == org_id
        assert run.status == RunStatus.DRAFT
        assert run.parent_run_id == parent_id
        assert run.run_relationship_type == RunRelationshipType.REPEAT_OF
        assert run.plate_format == PlateFormat.F384
        assert run.conditions == {"temperature": "37C"}
        assert run.qc_metrics is None
        assert run.is_locked is False
        assert run.locked_at is None
        assert run.locked_by is None
        assert run.lock_reason is None
        assert run.notes == "Test run"
        assert run.eln_entry_id is None
        assert run.plates == []
        assert run.wells == []
        assert run.version == 1

    def test_create_emits_run_created_event(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        events = run.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, RunCreated)
        assert evt.aggregate_id == run.id
        assert evt.aggregate_type == "Run"
        assert evt.protocol_id == protocol_id
        assert evt.operator == operator_id

    def test_parent_run_consistency_both_set(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        """Both parent_run_id and run_relationship_type set — OK."""
        run = _make_run(
            workspace_id,
            protocol_id,
            operator_id,
            parent_run_id=uuid.uuid4(),
            run_relationship_type=RunRelationshipType.CONFIRMATION_OF,
        )
        assert run.parent_run_id is not None
        assert run.run_relationship_type == RunRelationshipType.CONFIRMATION_OF

    def test_parent_run_consistency_both_null(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        """Both null — OK."""
        run = _make_run(workspace_id, protocol_id, operator_id)
        assert run.parent_run_id is None
        assert run.run_relationship_type is None

    def test_parent_run_only_raises(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        """parent_run_id set but run_relationship_type null — invalid."""
        with pytest.raises(ValidationError, match="both be set or both null"):
            _make_run(
                workspace_id,
                protocol_id,
                operator_id,
                parent_run_id=uuid.uuid4(),
            )

    def test_relationship_type_only_raises(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        """run_relationship_type set but parent_run_id null — invalid."""
        with pytest.raises(ValidationError, match="both be set or both null"):
            _make_run(
                workspace_id,
                protocol_id,
                operator_id,
                run_relationship_type=RunRelationshipType.FOLLOW_UP_TO,
            )


# ---------------------------------------------------------------------------
# TestRunStatusTransitions
# ---------------------------------------------------------------------------


class TestRunStatusTransitions:
    def test_full_lifecycle_to_approved(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        assert run.status == RunStatus.DRAFT

        run.start()
        assert run.status == RunStatus.IN_PROGRESS

        run.complete(plate_count=2, data_point_count=768)
        assert run.status == RunStatus.COMPLETED

        approver = uuid.uuid4()
        run.approve(approved_by=approver)
        assert run.status == RunStatus.APPROVED

    def test_reject_and_rework(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)

        reviewer = uuid.uuid4()
        run.reject(rejected_by=reviewer, reason="QC failed")
        assert run.status == RunStatus.REJECTED

        run.rework()
        assert run.status == RunStatus.DRAFT

    def test_cannot_skip_to_completed(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        with pytest.raises(ConflictError, match="Cannot transition"):
            run.complete(plate_count=1, data_point_count=96)

    def test_cannot_approve_draft(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        with pytest.raises(ConflictError, match="Cannot transition"):
            run.approve(approved_by=uuid.uuid4())

    def test_cannot_approve_in_progress(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        with pytest.raises(ConflictError, match="Cannot transition"):
            run.approve(approved_by=uuid.uuid4())

    def test_approved_is_terminal(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.approve(approved_by=uuid.uuid4())

        with pytest.raises(ConflictError, match="Cannot transition"):
            run.start()

    def test_reject_requires_reason(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)

        with pytest.raises(ValidationError, match="Rejection reason is required"):
            run.reject(rejected_by=uuid.uuid4(), reason="")

    def test_reject_whitespace_reason_raises(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)

        with pytest.raises(ValidationError, match="Rejection reason is required"):
            run.reject(rejected_by=uuid.uuid4(), reason="   ")

    def test_complete_emits_event(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.clear_events()

        run.complete(plate_count=4, data_point_count=1536)
        events = run.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, RunCompleted)
        assert evt.plate_count == 4
        assert evt.data_point_count == 1536

    def test_approve_emits_event(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.clear_events()

        approver = uuid.uuid4()
        run.approve(approved_by=approver)
        events = run.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, RunApproved)
        assert evt.approved_by == approver

    def test_reject_emits_event(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.clear_events()

        reviewer = uuid.uuid4()
        run.reject(rejected_by=reviewer, reason="Contamination detected")
        events = run.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, RunRejected)
        assert evt.rejected_by == reviewer
        assert evt.reason == "Contamination detected"


# ---------------------------------------------------------------------------
# TestRunLocking
# ---------------------------------------------------------------------------


class TestRunLocking:
    def test_lock_completed_run(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.clear_events()

        locker = uuid.uuid4()
        run.lock(locked_by=locker, reason="Data finalized")

        assert run.is_locked is True
        assert run.locked_by == locker
        assert run.lock_reason == "Data finalized"
        assert run.locked_at is not None

    def test_lock_approved_run(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.approve(approved_by=uuid.uuid4())

        run.lock(locked_by=uuid.uuid4(), reason="Approved and locked")
        assert run.is_locked is True

    def test_cannot_lock_draft(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        with pytest.raises(ConflictError, match="only completed or approved"):
            run.lock(locked_by=uuid.uuid4(), reason="Nope")

    def test_cannot_lock_in_progress(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        with pytest.raises(ConflictError, match="only completed or approved"):
            run.lock(locked_by=uuid.uuid4(), reason="Nope")

    def test_cannot_double_lock(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.lock(locked_by=uuid.uuid4(), reason="First lock")

        with pytest.raises(ConflictError, match="already locked"):
            run.lock(locked_by=uuid.uuid4(), reason="Second lock")

    def test_lock_requires_reason(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)

        with pytest.raises(ValidationError, match="Lock reason is required"):
            run.lock(locked_by=uuid.uuid4(), reason="")

    def test_lock_emits_event(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.clear_events()

        locker = uuid.uuid4()
        run.lock(locked_by=locker, reason="QC complete")
        events = run.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, RunLocked)
        assert evt.locked_by == locker
        assert evt.lock_reason == "QC complete"

    def test_unlock(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.lock(locked_by=uuid.uuid4(), reason="Locked")
        run.clear_events()

        unlocker = uuid.uuid4()
        run.unlock(unlocked_by=unlocker, reason="Correction needed")

        assert run.is_locked is False
        assert run.locked_at is None
        assert run.locked_by is None
        assert run.lock_reason is None

    def test_unlock_emits_event(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.lock(locked_by=uuid.uuid4(), reason="Locked")
        run.clear_events()

        unlocker = uuid.uuid4()
        run.unlock(unlocked_by=unlocker, reason="Re-analysis required")
        events = run.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, RunUnlocked)
        assert evt.unlocked_by == unlocker
        assert evt.reason == "Re-analysis required"

    def test_cannot_unlock_unlocked(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)

        with pytest.raises(ConflictError, match="not locked"):
            run.unlock(unlocked_by=uuid.uuid4(), reason="Nope")

    def test_add_plate_unlocked(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        plate = _make_plate(run.id, plate_number=1)
        old_updated = run.updated_at
        run.add_plate(plate)

        assert len(run.plates) == 1
        assert run.plates[0] == plate
        assert run.updated_at >= old_updated

    def test_record_qc_metrics_unlocked(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        metrics = {"z_prime": 0.75, "signal_to_background": 12.5}
        old_updated = run.updated_at
        run.record_qc_metrics(metrics)

        assert run.qc_metrics == metrics
        assert run.updated_at >= old_updated

    def test_locked_blocks_add_plate(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.lock(locked_by=uuid.uuid4(), reason="Finalized")

        plate = _make_plate(run.id)
        with pytest.raises(ConflictError, match="locked"):
            run.add_plate(plate)

    def test_locked_blocks_qc_metrics(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.lock(locked_by=uuid.uuid4(), reason="Finalized")

        with pytest.raises(ConflictError, match="locked"):
            run.record_qc_metrics({"z_prime": 0.75})


# ---------------------------------------------------------------------------
# TestRunUpdate
# ---------------------------------------------------------------------------


class TestRunUpdate:
    def test_update_conditions(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        old_updated = run.updated_at

        run.update(conditions={"Carbon Source": "glucose", "ATP": "10 uM"})

        assert run.conditions == {"Carbon Source": "glucose", "ATP": "10 uM"}
        assert run.updated_at >= old_updated

    def test_update_conditions_to_none_clears(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(
            workspace_id,
            protocol_id,
            operator_id,
            conditions={"Carbon Source": "glucose"},
        )

        run.update(conditions=None)

        assert run.conditions is None

    def test_update_notes_and_conditions_together(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)

        run.update(notes="rerun", conditions={"pH": "7.4"})

        assert run.notes == "rerun"
        assert run.conditions == {"pH": "7.4"}

    def test_update_rejects_unknown_field(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)

        with pytest.raises(ValidationError, match="Cannot update field"):
            run.update(run_date=date(2025, 1, 1))

    def test_locked_blocks_update_conditions(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        operator_id: uuid.UUID,
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.start()
        run.complete(plate_count=1, data_point_count=96)
        run.lock(locked_by=uuid.uuid4(), reason="Finalized")

        with pytest.raises(ConflictError, match="locked"):
            run.update(conditions={"pH": "7.4"})


# ---------------------------------------------------------------------------
# TestPlate
# ---------------------------------------------------------------------------


class TestPlate:
    def test_create_plate(self) -> None:
        run_id = uuid.uuid4()
        plate = Plate(
            run_id=run_id,
            plate_number=3,
            barcode=Barcode(value="PLT-00003"),
            format=PlateFormat.F96,
            plate_map={"A1": "sample", "H12": "control"},
        )

        assert plate.run_id == run_id
        assert plate.plate_number == 3
        assert plate.barcode == Barcode(value="PLT-00003")
        assert plate.format == PlateFormat.F96
        assert plate.plate_map == {"A1": "sample", "H12": "control"}
        assert plate.parent_plate_id is None
        assert plate.template_id is None
        assert plate.registered_plate_id is None

    def test_invalid_plate_number_zero(self) -> None:
        with pytest.raises(ValidationError, match="plate_number must be >= 1"):
            Plate(run_id=uuid.uuid4(), plate_number=0)

    def test_invalid_plate_number_negative(self) -> None:
        with pytest.raises(ValidationError, match="plate_number must be >= 1"):
            Plate(run_id=uuid.uuid4(), plate_number=-1)


# ---------------------------------------------------------------------------
# TestWell
# ---------------------------------------------------------------------------


class TestWell:
    def test_create_well(self) -> None:
        plate_id = uuid.uuid4()
        batch_id = uuid.uuid4()

        well = Well(
            plate_id=plate_id,
            row="B",
            column=5,
            well_type=WellType.SAMPLE,
            batch_id=batch_id,
            dose=10.0,
        )

        assert well.plate_id == plate_id
        assert well.row == "B"
        assert well.column == 5
        assert well.well_type == WellType.SAMPLE
        assert well.batch_id == batch_id
        assert well.dose == 10.0

    def test_row_uppercased(self) -> None:
        well = Well(plate_id=uuid.uuid4(), row="a", column=1)
        assert well.row == "A"

    def test_two_char_row(self) -> None:
        well = Well(plate_id=uuid.uuid4(), row="af", column=1)
        assert well.row == "AF"

    def test_invalid_column_zero(self) -> None:
        with pytest.raises(ValidationError, match="column must be >= 1"):
            Well(plate_id=uuid.uuid4(), row="A", column=0)

    def test_invalid_column_negative(self) -> None:
        with pytest.raises(ValidationError, match="column must be >= 1"):
            Well(plate_id=uuid.uuid4(), row="A", column=-1)

    @pytest.mark.parametrize("dose", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_dose_raises(self, dose: float) -> None:
        with pytest.raises(ValidationError, match=r"^Concentration must be a finite number$"):
            Well(plate_id=uuid.uuid4(), row="A", column=1, dose=dose)

    def test_empty_row_raises(self) -> None:
        with pytest.raises(ValidationError, match="1-2 alphabetic"):
            Well(plate_id=uuid.uuid4(), row="", column=1)

    def test_three_char_row_raises(self) -> None:
        with pytest.raises(ValidationError, match="1-2 alphabetic"):
            Well(plate_id=uuid.uuid4(), row="ABC", column=1)

    def test_numeric_row_raises(self) -> None:
        with pytest.raises(ValidationError, match="1-2 alphabetic"):
            Well(plate_id=uuid.uuid4(), row="1", column=1)

    def test_all_well_types(self) -> None:
        """All WellType variants can be assigned."""
        plate_id = uuid.uuid4()
        for wt in WellType:
            well = Well(plate_id=plate_id, row="A", column=1, well_type=wt)
            assert well.well_type == wt


# ---------------------------------------------------------------------------
# Hit criteria — per-run, attributable analytical decision
# ---------------------------------------------------------------------------


def _completed_run(workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID) -> Run:
    run = _make_run(workspace_id, protocol_id, operator_id)
    run.start()
    run.complete(plate_count=1, data_point_count=96)
    run.clear_events()
    return run


class TestRunHitCriteria:
    def test_run_starts_with_hit_criteria_unset(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        assert run.hit_criteria is None
        assert run.hit_criteria_set_by is None
        assert run.hit_criteria_set_at is None

    def test_set_hit_criteria_records_criteria_and_provenance(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        screener = uuid.uuid4()
        criteria = [HitCriterion(readout_name="% Inhibition", operator="gt", value=50.0)]

        run.set_hit_criteria(criteria, set_by=screener)

        assert run.hit_criteria == criteria
        assert run.hit_criteria_set_by == screener
        assert run.hit_criteria_set_at is not None

    def test_set_empty_criteria_is_a_recorded_show_all_decision(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        """An empty list is a deliberate "no threshold" decision — distinct
        from unset (None) — and still carries provenance."""
        run = _make_run(workspace_id, protocol_id, operator_id)
        screener = uuid.uuid4()

        run.set_hit_criteria([], set_by=screener)

        assert run.hit_criteria == []
        assert run.hit_criteria is not None
        assert run.hit_criteria_set_by == screener
        assert run.hit_criteria_set_at is not None

    def test_set_hit_criteria_emits_event(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.clear_events()
        screener = uuid.uuid4()
        criteria = [
            HitCriterion(readout_name="% Inhibition", operator="gt", value=50.0),
            HitCriterion(readout_name="Curve Class", operator="in", value=["full"]),
        ]

        run.set_hit_criteria(criteria, set_by=screener)

        events = run.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], RunHitCriteriaSet)
        assert events[0].set_by == screener
        assert events[0].rule_count == 2

    def test_clear_hit_criteria_reverts_to_unset(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.set_hit_criteria(
            [HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
            set_by=uuid.uuid4(),
        )

        run.clear_hit_criteria(cleared_by=uuid.uuid4())

        assert run.hit_criteria is None
        assert run.hit_criteria_set_by is None
        assert run.hit_criteria_set_at is None

    def test_clear_hit_criteria_emits_event(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.set_hit_criteria([], set_by=uuid.uuid4())
        run.clear_events()
        clearer = uuid.uuid4()

        run.clear_hit_criteria(cleared_by=clearer)

        events = run.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], RunHitCriteriaCleared)
        assert events[0].cleared_by == clearer

    def test_set_hit_criteria_blocked_when_locked(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _completed_run(workspace_id, protocol_id, operator_id)
        run.lock(locked_by=uuid.uuid4(), reason="Finalized")

        with pytest.raises(ConflictError, match="locked"):
            run.set_hit_criteria(
                [HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
                set_by=uuid.uuid4(),
            )

    def test_clear_hit_criteria_blocked_when_locked(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _completed_run(workspace_id, protocol_id, operator_id)
        run.set_hit_criteria([], set_by=uuid.uuid4())
        run.lock(locked_by=uuid.uuid4(), reason="Finalized")

        with pytest.raises(ConflictError, match="locked"):
            run.clear_hit_criteria(cleared_by=uuid.uuid4())

    def test_set_hit_criteria_enforces_max_rules(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        too_many = [
            HitCriterion(readout_name=f"R{i}", operator="gt", value=float(i)) for i in range(4)
        ]
        with pytest.raises(ValidationError, match="Maximum"):
            run.set_hit_criteria(too_many, set_by=uuid.uuid4())


# ---------------------------------------------------------------------------
# TestRunPlateLink — optional link from a run plate to the inventory plate
# ---------------------------------------------------------------------------


class TestRunPlateLink:
    def test_link_plate_sets_and_clears_registered_plate(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        plate = _make_plate(run.id)
        run.add_plate(plate)
        target = uuid.uuid4()
        old_updated = run.updated_at

        run.link_plate(plate.id, target)
        assert plate.registered_plate_id == target
        assert run.updated_at >= old_updated

        run.link_plate(plate.id, None)
        assert plate.registered_plate_id is None

    def test_link_plate_unknown_plate_is_not_found(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _make_run(workspace_id, protocol_id, operator_id)
        run.add_plate(_make_plate(run.id))

        with pytest.raises(NotFoundError, match="Plate"):
            run.link_plate(uuid.uuid4(), uuid.uuid4())

    def test_link_plate_blocked_when_locked(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, operator_id: uuid.UUID
    ) -> None:
        run = _completed_run(workspace_id, protocol_id, operator_id)
        plate = _make_plate(run.id)
        run.add_plate(plate)
        run.lock(locked_by=uuid.uuid4(), reason="Finalized")

        with pytest.raises(ConflictError, match="locked"):
            run.link_plate(plate.id, uuid.uuid4())
        assert plate.registered_plate_id is None


# ---------------------------------------------------------------------------
# Holder kind, holder size, well label
# ---------------------------------------------------------------------------

_RUN = uuid.uuid4()
_P = uuid.uuid4()


def test_plate_defaults_to_plate_holder():
    p = Plate(run_id=uuid.uuid4(), plate_number=1)
    assert (p.holder_kind, p.holder_rows, p.holder_columns) == (HolderKind.PLATE, None, None)


def test_cassette_needs_one_row_and_no_format():
    Plate(
        run_id=_RUN,
        plate_number=1,
        holder_kind=HolderKind.CASSETTE,
        holder_rows=1,
        holder_columns=48,
    )
    with pytest.raises(ValidationError):
        Plate(
            run_id=_RUN,
            plate_number=1,
            holder_kind=HolderKind.CASSETTE,
            holder_rows=2,
            holder_columns=12,
        )
    with pytest.raises(ValidationError):
        Plate(
            run_id=_RUN,
            plate_number=1,
            holder_kind=HolderKind.CASSETTE,
            holder_rows=1,
            holder_columns=24,
            format=PlateFormat.F24,
        )


def test_holder_size_is_both_or_neither_and_positive():
    for rows, cols in ((1, None), (None, 5), (0, 5), (1, 0)):
        with pytest.raises(ValidationError):
            Plate(run_id=_RUN, plate_number=1, holder_rows=rows, holder_columns=cols)


def test_well_label_is_trimmed_capped_and_blank_is_none():
    assert Well(plate_id=_P, row="A", column=1, label="  x  ").label == "x"
    assert Well(plate_id=_P, row="A", column=1, label="   ").label is None
    assert len(Well(plate_id=_P, row="A", column=1, label="x" * 200).label) == 200
    with pytest.raises(ValidationError, match=r"^Position label must be at most 200 characters$"):
        Well(plate_id=_P, row="A", column=1, label="x" * 201)


def test_well_note_is_trimmed_capped_and_blank_is_none():
    assert Well(plate_id=_P, row="A", column=1, note="  went cloudy  ").note == "went cloudy"
    assert Well(plate_id=_P, row="A", column=1, note="   ").note is None
    assert Well(plate_id=_P, row="A", column=1).note is None
    assert len(Well(plate_id=_P, row="A", column=1, note="x" * 1000).note) == 1000
    with pytest.raises(ValidationError, match=r"^Position note must be at most 1000 characters$"):
        Well(plate_id=_P, row="A", column=1, note="x" * 1001)


def test_position_above_24_is_a_valid_well():
    assert Well(plate_id=_P, row="A", column=48).column == 48


# ---------------------------------------------------------------------------
# Instrument import event
# ---------------------------------------------------------------------------


def _fresh_run() -> Run:
    run = Run.create(
        workspace_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_date=date(2025, 6, 15),
        operator=uuid.uuid4(),
    )
    run.clear_events()
    return run


def test_record_instrument_import_registers_event():
    run = _fresh_run()
    run.record_instrument_import(
        reader="r", file_name="f.xlsx", positions=3, curves=6, readout_values=4
    )
    (event,) = [e for e in run.collect_events() if isinstance(e, RunInstrumentFileImported)]
    assert (
        event.reader,
        event.file_name,
        event.positions,
        event.curves,
        event.readout_values,
    ) == (
        "r",
        "f.xlsx",
        3,
        6,
        4,
    )
    assert event.aggregate_id == run.id
    assert event.aggregate_type == "Run"
    assert event.workspace_id == run.workspace_id


def test_record_instrument_import_blocked_when_locked():
    run = _fresh_run()
    run.start()
    run.complete(plate_count=1, data_point_count=1)
    run.lock(locked_by=uuid.uuid4(), reason="final")
    with pytest.raises(ConflictError):
        run.record_instrument_import(
            reader="r", file_name="f.xlsx", positions=1, curves=1, readout_values=1
        )


def test_clear_plate_format():
    run = _fresh_run()
    run.plate_format = PlateFormat.F96
    run.clear_plate_format()
    assert run.plate_format is None


def test_clear_plate_format_blocked_when_locked():
    run = _fresh_run()
    run.plate_format = PlateFormat.F96
    run.start()
    run.complete(plate_count=0, data_point_count=0)
    run.lock(locked_by=uuid.uuid4(), reason="final")
    with pytest.raises(ConflictError):
        run.clear_plate_format()
    assert run.plate_format == PlateFormat.F96


def test_reset_data_event_carries_measured_curve_count():
    run = _fresh_run()
    run.reset_data(readouts_deleted=1, curves_deleted=0, measured_curves_deleted=96)
    event = next(e for e in run.collect_events() if isinstance(e, RunDataReset))
    assert event.measured_curves_deleted == 96


# ---------------------------------------------------------------------------
# Relabel positions
# ---------------------------------------------------------------------------


def _instrument_run(
    status: RunStatus = RunStatus.DRAFT, locked: bool = False
) -> tuple[Run, list[Well]]:
    """One cassette of three positions: a reference, a sample with a batch, a bare sample."""
    run_id = uuid.uuid4()
    plate = Plate(
        run_id=run_id,
        plate_number=1,
        holder_kind=HolderKind.CASSETTE,
        holder_rows=1,
        holder_columns=3,
    )
    wells = [
        Well(
            plate_id=plate.id,
            row="A",
            column=1,
            well_type=WellType.REFERENCE,
            label="protein alone",
        ),
        Well(plate_id=plate.id, row="A", column=2, batch_id=uuid.uuid4(), dose=10.0, label="x"),
        Well(plate_id=plate.id, row="A", column=3),
    ]
    run = Run(
        id=run_id,
        workspace_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_date=date(2025, 6, 15),
        operator=uuid.uuid4(),
        status=status,
        is_locked=locked,
        plates=[plate],
        wells=wells,
    )
    return run, wells


def E(w: Well, **new) -> PositionEdit:
    return PositionEdit(w.id, w.values, replace(w.values, **new))


def P(n: int) -> str:
    return position_label(HolderKind.CASSETTE, "A", n)


def test_relabel_changes_fields_and_registers_one_event():
    run, (_, w2, w3) = _instrument_run()
    changes = run.relabel_positions([E(w2, label="y", dose=25.0), E(w3, note="bubble")])
    assert (w2.label, w2.dose, w3.note) == ("y", 25.0, "bubble")
    (event,) = [e for e in run.collect_events() if isinstance(e, RunPositionsRelabelled)]
    assert event.positions == changes and len(changes) == 2 and event.aggregate_id == run.id
    assert event.aggregate_type == "Run" and event.workspace_id == run.workspace_id
    assert changes[0].position_label == P(2)
    assert changes[0].fields == (
        FieldChange("label", "x", "y"),
        FieldChange("concentration", "10.0", "25.0"),
    )
    assert event.audit_changes()[0] == (f"{P(2)}: label", "x", "y")
    assert len(event.audit_changes()) == 3
    assert not changes[0].batch_changed and changes[0].touches_calculation
    assert not changes[1].touches_calculation


@pytest.mark.parametrize(
    "old,new,old_text,new_text",
    [
        (0.1234567, 0.1234568, "0.1234567", "0.1234568"),
        (11.1111111, 1234567.0, "11.1111111", "1234567.0"),
    ],
)
def test_relabel_audit_text_keeps_every_digit_of_a_concentration(old, new, old_text, new_text):
    run, (_, w2, _) = _instrument_run()
    w2.dose = old
    (change,) = run.relabel_positions([E(w2, dose=new)])
    assert change.fields == (FieldChange("concentration", old_text, new_text),)


def test_check_position_edits_refuses_a_stale_edit_and_changes_nothing():
    run, (_, w2, w3) = _instrument_run()
    stale = PositionEdit(w2.id, replace(w2.values, label="old"), replace(w2.values, batch_id=None))
    with pytest.raises(StaleEditError, match=P(2)):
        run.check_position_edits([E(w3, note="n"), stale])
    run.check_position_edits([E(w2, batch_id=None), E(w3, note="n")])
    assert (w2.batch_id is not None, w3.note) == (True, None) and run.collect_events() == []


def test_relabel_batch_change_uses_batch_names_and_flags_calculation():
    run, (_, w2, _) = _instrument_run()
    other = uuid.uuid4()
    changes = run.relabel_positions(
        [E(w2, batch_id=other)], batch_names={w2.batch_id: "B-1", other: "B-2"}
    )
    assert changes[0].fields == (FieldChange("batch", "B-1", "B-2"),)
    assert changes[0].batch_changed and changes[0].touches_calculation
    assert w2.batch_id == other


def test_relabel_batch_without_names_uses_the_id_and_none_for_no_batch():
    run, (_, w2, _) = _instrument_run()
    old = w2.batch_id
    changes = run.relabel_positions([E(w2, batch_id=None)])
    assert changes[0].fields == (FieldChange("batch", str(old), None),)


def test_relabel_with_no_changes_registers_nothing():
    run, (_, w2, w3) = _instrument_run()
    before = run.updated_at
    assert run.relabel_positions([E(w2), E(w3, label="  ")]) == ()
    assert run.collect_events() == []
    assert run.updated_at == before


def test_relabel_stale_expected_is_conflict_naming_positions_and_changes_nothing():
    run, (_, w2, w3) = _instrument_run()
    stale = PositionEdit(
        w2.id,
        replace(w2.values, label="what it used to say"),
        replace(w2.values, label="mine"),
    )
    with pytest.raises(ConflictError, match=P(2)) as exc:
        run.relabel_positions([E(w3, note="n"), stale])
    assert P(3) not in str(exc.value)
    # Says what reloading costs: the edits not yet saved.
    assert exc.value.message == (
        f"Changed by someone else since you opened them: {P(2)}. "
        "Reloading shows their current values and discards your unsaved edits."
    )
    assert (w2.label, w3.note) == ("x", None) and run.collect_events() == []


def test_relabel_expected_is_normalised_before_the_stale_check():
    run, (_, w2, _) = _instrument_run()
    edit = PositionEdit(w2.id, replace(w2.values, label="  x "), replace(w2.values, label="y"))
    assert len(run.relabel_positions([edit])) == 1


@pytest.mark.parametrize("new", [{"well_type": WellType.BLANK}, {"batch_id": None}, {"dose": 5.0}])
@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.APPROVED, RunStatus.REJECTED])
def test_relabel_role_batch_or_concentration_refused_outside_draft_or_in_progress(new, status):
    run, (_, w2, _) = _instrument_run(status=status)
    before = w2.values
    with pytest.raises(ConflictError, match="draft or in progress"):
        run.relabel_positions([E(w2, **new)], reason="typo")
    assert w2.values == before and run.collect_events() == []


@pytest.mark.parametrize("status", [RunStatus.DRAFT, RunStatus.IN_PROGRESS])
def test_relabel_role_batch_and_concentration_allowed_in_draft_and_in_progress(status):
    run, (_, w2, _) = _instrument_run(status=status)
    run.relabel_positions([E(w2, well_type=WellType.BLANK, batch_id=None, dose=5.0)])
    assert (w2.well_type, w2.batch_id, w2.dose) == (WellType.BLANK, None, 5.0)


def test_relabel_label_on_completed_run_needs_a_reason_and_keeps_it():
    run, (_, w2, _) = _instrument_run(status=RunStatus.COMPLETED)
    with pytest.raises(ValidationError, match="reason"):
        run.relabel_positions([E(w2, label="y")])
    with pytest.raises(ValidationError, match="reason"):
        run.relabel_positions([E(w2, label="y")], reason="   ")
    assert w2.label == "x"
    run.relabel_positions([E(w2, label="y")], reason="  typo in the name ")
    (event,) = [e for e in run.collect_events() if isinstance(e, RunPositionsRelabelled)]
    assert event.reason == "typo in the name" and event.audit_reason == "typo in the name"
    assert w2.label == "y"


def test_relabel_note_on_rejected_run_needs_no_reason():
    run, (_, w2, _) = _instrument_run(status=RunStatus.REJECTED)
    run.relabel_positions([E(w2, note="n")])
    assert w2.note == "n"


def test_relabel_on_draft_run_needs_no_reason():
    run, (_, w2, _) = _instrument_run()
    run.relabel_positions([E(w2, label="y")], reason="   ")
    (event,) = [e for e in run.collect_events() if isinstance(e, RunPositionsRelabelled)]
    assert event.reason is None and event.audit_reason is None


def test_relabel_blocked_when_locked():
    run, (_, w2, _) = _instrument_run(status=RunStatus.COMPLETED, locked=True)
    with pytest.raises(ConflictError, match="locked"):
        run.relabel_positions([E(w2, label="y")], reason="typo")
    assert w2.label == "x" and run.collect_events() == []


@pytest.mark.parametrize(
    "new", [{"label": "x" * 201}, {"note": "n" * 1001}, {"dose": -1.0}, {"dose": float("nan")}]
)
def test_relabel_validates_like_a_well(new):
    run, (_, w2, w3) = _instrument_run()
    with pytest.raises(ValidationError) as exc:
        run.relabel_positions([E(w3, note="fine"), E(w2, **new)])
    assert str(exc.value).startswith(P(2))
    assert w3.note is None and run.collect_events() == []


def test_relabel_unknown_or_repeated_position_is_validation_error():
    run, (_, w2, _) = _instrument_run()
    unknown = PositionEdit(uuid.uuid4(), w2.values, replace(w2.values, label="y"))
    with pytest.raises(ValidationError):
        run.relabel_positions([unknown])
    # A repeated position is named by its label, not its identifier.
    with pytest.raises(ValidationError, match=f"^{P(2)} is given more than once$"):
        run.relabel_positions([E(w2, label="y"), E(w2, label="z")])
    assert w2.label == "x" and run.collect_events() == []


def test_well_values_reflects_the_stored_fields():
    _, (w1, w2, _) = _instrument_run()
    assert w1.values == PositionValues(label="protein alone", well_type=WellType.REFERENCE)
    assert w2.values == PositionValues(label="x", batch_id=w2.batch_id, dose=10.0)
