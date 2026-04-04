"""Tests for BulkDisclosure aggregate root."""

import uuid

import pytest

from chem_vault.domain.chemical_registration.bulk_disclosure import BulkDisclosure
from chem_vault.domain.chemical_registration.enums import BulkDisclosureStatus
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


def _make(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    total_count: int = 5,
) -> BulkDisclosure:
    """Create a BulkDisclosure in PROCESSING state for transition tests."""
    bd = BulkDisclosure.create(
        source_file="compounds.csv",
        partner_org_id=org_id,
        submitted_by=user_id,
        total_count=total_count,
    )
    bd.start_processing()
    return bd


# ---------------------------------------------------------------------------
# TestBulkDisclosureCreation
# ---------------------------------------------------------------------------


class TestBulkDisclosureCreation:
    def test_create_sets_all_fields(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = BulkDisclosure.create(
            source_file="compounds.csv",
            partner_org_id=org_id,
            submitted_by=user_id,
            total_count=10,
        )

        assert bd.source_file == "compounds.csv"
        assert bd.partner_org_id == org_id
        assert bd.submitted_by == user_id
        assert bd.submitted_at is not None
        assert bd.status == BulkDisclosureStatus.PENDING
        assert bd.total_count == 10
        assert bd.disclosed_count == 0
        assert bd.merged_count == 0
        assert bd.conflict_count == 0
        assert bd.error_count == 0
        assert bd.processed_count == 0
        assert bd.completed_at is None
        assert bd.version == 1

    def test_create_with_zero_count_raises(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="total_count must be greater than zero"):
            BulkDisclosure.create(
                source_file="compounds.csv",
                partner_org_id=org_id,
                submitted_by=user_id,
                total_count=0,
            )

    def test_create_with_negative_count_raises(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="total_count must be greater than zero"):
            BulkDisclosure.create(
                source_file="compounds.csv",
                partner_org_id=org_id,
                submitted_by=user_id,
                total_count=-1,
            )

    def test_create_with_empty_file_raises(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="source_file must not be empty"):
            BulkDisclosure.create(
                source_file="",
                partner_org_id=org_id,
                submitted_by=user_id,
                total_count=5,
            )

    def test_create_with_whitespace_file_raises(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="source_file must not be empty"):
            BulkDisclosure.create(
                source_file="   ",
                partner_org_id=org_id,
                submitted_by=user_id,
                total_count=5,
            )

    def test_source_file_is_stripped(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = BulkDisclosure.create(
            source_file="  compounds.csv  ",
            partner_org_id=org_id,
            submitted_by=user_id,
            total_count=5,
        )
        assert bd.source_file == "compounds.csv"


# ---------------------------------------------------------------------------
# TestBulkDisclosureProgress
# ---------------------------------------------------------------------------


class TestBulkDisclosureProgress:
    def test_start_processing(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = BulkDisclosure.create(
            source_file="compounds.csv",
            partner_org_id=org_id,
            submitted_by=user_id,
            total_count=5,
        )
        bd.start_processing()

        assert bd.status == BulkDisclosureStatus.PROCESSING

    def test_record_disclosed(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=3)
        bd.record_disclosed()

        assert bd.disclosed_count == 1
        assert bd.processed_count == 1

    def test_record_merged(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=3)
        bd.record_merged()

        assert bd.merged_count == 1
        assert bd.processed_count == 1

    def test_record_conflict(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=3)
        bd.record_conflict()

        assert bd.conflict_count == 1
        assert bd.processed_count == 1

    def test_record_error(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=3)
        bd.record_error()

        assert bd.error_count == 1
        assert bd.processed_count == 1

    def test_complete_all_success(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=3)
        bd.record_disclosed()
        bd.record_disclosed()
        bd.record_merged()

        bd.complete()

        assert bd.status == BulkDisclosureStatus.COMPLETED
        assert bd.completed_at is not None

    def test_complete_with_errors(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=4)
        bd.record_disclosed()
        bd.record_merged()
        bd.record_conflict()
        bd.record_error()

        bd.complete()

        assert bd.status == BulkDisclosureStatus.COMPLETED_WITH_ERRORS
        assert bd.completed_at is not None

    def test_complete_with_only_conflicts(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=2)
        bd.record_disclosed()
        bd.record_conflict()

        bd.complete()

        assert bd.status == BulkDisclosureStatus.COMPLETED_WITH_ERRORS

    def test_complete_with_only_errors(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=2)
        bd.record_disclosed()
        bd.record_error()

        bd.complete()

        assert bd.status == BulkDisclosureStatus.COMPLETED_WITH_ERRORS

    def test_complete_count_mismatch_raises(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=5)
        bd.record_disclosed()
        bd.record_disclosed()
        # only 2 of 5 processed

        with pytest.raises(ValidationError, match="processed 2 of 5"):
            bd.complete()

    def test_cannot_start_processing_when_not_pending(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=1)
        # already PROCESSING from _make

        with pytest.raises(ValidationError, match="Cannot transition bulk disclosure status"):
            bd.start_processing()

    def test_cannot_record_when_not_processing(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = BulkDisclosure.create(
            source_file="compounds.csv",
            partner_org_id=org_id,
            submitted_by=user_id,
            total_count=5,
        )
        # still PENDING

        with pytest.raises(ValidationError, match="Can only record results while"):
            bd.record_disclosed()

    def test_cannot_record_after_completed(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=1)
        bd.record_disclosed()
        bd.complete()

        with pytest.raises(ValidationError, match="Can only record results while"):
            bd.record_disclosed()

    def test_processed_count_accumulates(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = _make(org_id, user_id, total_count=6)
        bd.record_disclosed()
        bd.record_disclosed()
        bd.record_merged()
        bd.record_conflict()
        bd.record_error()

        assert bd.disclosed_count == 2
        assert bd.merged_count == 1
        assert bd.conflict_count == 1
        assert bd.error_count == 1
        assert bd.processed_count == 5

    def test_transitions_update_updated_at(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        bd = BulkDisclosure.create(
            source_file="compounds.csv",
            partner_org_id=org_id,
            submitted_by=user_id,
            total_count=1,
        )
        initial_updated = bd.updated_at

        bd.start_processing()
        assert bd.updated_at >= initial_updated

        after_processing = bd.updated_at
        bd.record_disclosed()
        assert bd.updated_at >= after_processing

        after_record = bd.updated_at
        bd.complete()
        assert bd.updated_at >= after_record
