"""Tests for Run aggregate root, Plate, and Well entities."""

import uuid
from datetime import date

import pytest

from cellar.domain.screening_assay.enums import (
    PlateFormat,
    RunRelationshipType,
    RunStatus,
    WellType,
)
from cellar.domain.screening_assay.events import (
    RunApproved,
    RunCompleted,
    RunCreated,
    RunLocked,
    RunRejected,
    RunUnlocked,
)
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.shared.value_objects import Barcode, Concentration


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
