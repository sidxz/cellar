"""Tests for BulkRegistration aggregate root."""

import uuid

import pytest

from chem_vault.domain.chemical_registration.bulk_registration import BulkRegistration
from chem_vault.domain.chemical_registration.enums import (
    BulkRegistrationFileFormat,
    BulkRegistrationStatus,
)
from chem_vault.domain.chemical_registration.events import (
    BulkRegistrationCompleted,
    BulkRegistrationStarted,
)
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


def _make(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    total_count: int = 5,
    file_format: BulkRegistrationFileFormat = BulkRegistrationFileFormat.SDF,
) -> BulkRegistration:
    """Create a BulkRegistration in PROCESSING state for transition tests."""
    br = BulkRegistration.create(
        workspace_id=workspace_id,
        source_file="compounds.sdf",
        file_format=file_format,
        submitted_by=user_id,
        total_count=total_count,
    )
    br.clear_events()
    br.start_processing()
    return br


# ---------------------------------------------------------------------------
# TestBulkRegistrationCreation
# ---------------------------------------------------------------------------


class TestBulkRegistrationCreation:
    def test_create_sets_all_fields(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = BulkRegistration.create(
            workspace_id=workspace_id,
            source_file="compounds.sdf",
            file_format=BulkRegistrationFileFormat.SDF,
            submitted_by=user_id,
            total_count=10,
        )

        assert br.workspace_id == workspace_id
        assert br.source_file == "compounds.sdf"
        assert br.file_format == BulkRegistrationFileFormat.SDF
        assert br.submitted_by == user_id
        assert br.submitted_at is not None
        assert br.status == BulkRegistrationStatus.PENDING
        assert br.total_count == 10
        assert br.registered_count == 0
        assert br.duplicate_count == 0
        assert br.error_count == 0
        assert br.processed_count == 0
        assert br.completed_at is None
        assert br.version == 1

    def test_create_emits_started_event(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = BulkRegistration.create(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format=BulkRegistrationFileFormat.CSV,
            submitted_by=user_id,
            total_count=5,
        )
        events = br.collect_events()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, BulkRegistrationStarted)
        assert evt.workspace_id == workspace_id
        assert evt.source_file == "compounds.csv"
        assert evt.file_format == "csv"
        assert evt.total_count == 5
        assert evt.submitted_by == user_id

    def test_create_with_zero_count_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="total_count must be greater than zero"):
            BulkRegistration.create(
                workspace_id=workspace_id,
                source_file="compounds.sdf",
                file_format=BulkRegistrationFileFormat.SDF,
                submitted_by=user_id,
                total_count=0,
            )

    def test_create_with_negative_count_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="total_count must be greater than zero"):
            BulkRegistration.create(
                workspace_id=workspace_id,
                source_file="compounds.sdf",
                file_format=BulkRegistrationFileFormat.SDF,
                submitted_by=user_id,
                total_count=-1,
            )

    def test_create_with_empty_file_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="source_file must not be empty"):
            BulkRegistration.create(
                workspace_id=workspace_id,
                source_file="",
                file_format=BulkRegistrationFileFormat.SDF,
                submitted_by=user_id,
                total_count=5,
            )

    def test_create_with_whitespace_file_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="source_file must not be empty"):
            BulkRegistration.create(
                workspace_id=workspace_id,
                source_file="   ",
                file_format=BulkRegistrationFileFormat.SDF,
                submitted_by=user_id,
                total_count=5,
            )

    def test_source_file_is_stripped(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = BulkRegistration.create(
            workspace_id=workspace_id,
            source_file="  compounds.xlsx  ",
            file_format=BulkRegistrationFileFormat.XLSX,
            submitted_by=user_id,
            total_count=5,
        )
        assert br.source_file == "compounds.xlsx"

    def test_all_file_formats(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        for fmt in BulkRegistrationFileFormat:
            br = BulkRegistration.create(
                workspace_id=workspace_id,
                source_file=f"compounds.{fmt.value}",
                file_format=fmt,
                submitted_by=user_id,
                total_count=1,
            )
            assert br.file_format == fmt


# ---------------------------------------------------------------------------
# TestBulkRegistrationProgress
# ---------------------------------------------------------------------------


class TestBulkRegistrationProgress:
    def test_start_processing(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = BulkRegistration.create(
            workspace_id=workspace_id,
            source_file="compounds.sdf",
            file_format=BulkRegistrationFileFormat.SDF,
            submitted_by=user_id,
            total_count=5,
        )
        br.start_processing()
        assert br.status == BulkRegistrationStatus.PROCESSING

    def test_record_registered(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=3)
        br.record_registered()
        assert br.registered_count == 1
        assert br.processed_count == 1

    def test_record_duplicate(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=3)
        br.record_duplicate()
        assert br.duplicate_count == 1
        assert br.processed_count == 1

    def test_record_error(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=3)
        br.record_error()
        assert br.error_count == 1
        assert br.processed_count == 1

    def test_complete_all_success(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=3)
        br.record_registered()
        br.record_registered()
        br.record_duplicate()
        br.complete()
        assert br.status == BulkRegistrationStatus.COMPLETED
        assert br.completed_at is not None

    def test_complete_emits_event(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=2)
        br.record_registered()
        br.record_duplicate()
        br.complete()

        events = br.collect_events()
        completed_events = [e for e in events if isinstance(e, BulkRegistrationCompleted)]
        assert len(completed_events) == 1
        evt = completed_events[0]
        assert evt.registered_count == 1
        assert evt.duplicate_count == 1
        assert evt.error_count == 0

    def test_complete_with_errors(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=3)
        br.record_registered()
        br.record_duplicate()
        br.record_error()
        br.complete()
        assert br.status == BulkRegistrationStatus.COMPLETED_WITH_ERRORS
        assert br.completed_at is not None

    def test_complete_count_mismatch_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=5)
        br.record_registered()
        br.record_registered()
        with pytest.raises(ValidationError, match="processed 2 of 5"):
            br.complete()

    def test_cannot_start_processing_when_not_pending(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=1)
        with pytest.raises(ValidationError, match="Cannot transition bulk registration"):
            br.start_processing()

    def test_cannot_record_when_not_processing(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = BulkRegistration.create(
            workspace_id=workspace_id,
            source_file="compounds.sdf",
            file_format=BulkRegistrationFileFormat.SDF,
            submitted_by=user_id,
            total_count=5,
        )
        with pytest.raises(ValidationError, match="Can only record results while"):
            br.record_registered()

    def test_cannot_record_after_completed(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=1)
        br.record_registered()
        br.complete()
        with pytest.raises(ValidationError, match="Can only record results while"):
            br.record_registered()

    def test_processed_count_accumulates(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = _make(workspace_id, user_id, total_count=6)
        br.record_registered()
        br.record_registered()
        br.record_registered()
        br.record_duplicate()
        br.record_error()
        assert br.registered_count == 3
        assert br.duplicate_count == 1
        assert br.error_count == 1
        assert br.processed_count == 5

    def test_transitions_update_updated_at(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        br = BulkRegistration.create(
            workspace_id=workspace_id,
            source_file="compounds.sdf",
            file_format=BulkRegistrationFileFormat.SDF,
            submitted_by=user_id,
            total_count=1,
        )
        initial_updated = br.updated_at
        br.start_processing()
        assert br.updated_at >= initial_updated

        after_processing = br.updated_at
        br.record_registered()
        assert br.updated_at >= after_processing

        after_record = br.updated_at
        br.complete()
        assert br.updated_at >= after_record
