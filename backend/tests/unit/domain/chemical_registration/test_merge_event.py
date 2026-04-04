"""Tests for MergeEvent entity."""

import uuid

import pytest

from chem_vault.domain.chemical_registration.enums import MergeReason
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def source_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def target_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def snapshot() -> dict:
    return {"smiles": "CCO", "name": "Ethanol", "reg_number": "CV-00001"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMergeEventCreate:
    """MergeEvent.create() factory tests."""

    def test_create(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot: dict,
    ) -> None:
        event = MergeEvent.create(
            source_molecule_id=source_id,
            target_molecule_id=target_id,
            reason=MergeReason.MANUAL_MERGE,
            merged_by=user_id,
            snapshot=snapshot,
        )

        assert event.source_molecule_id == source_id
        assert event.target_molecule_id == target_id
        assert event.reason == MergeReason.MANUAL_MERGE
        assert event.merged_by == user_id
        assert event.snapshot == snapshot
        assert event.disclosure_request_id is None
        assert event.notes is None
        assert event.merged_at is not None

    def test_create_with_disclosure_ref(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot: dict,
    ) -> None:
        disc_id = uuid.uuid4()
        event = MergeEvent.create(
            source_molecule_id=source_id,
            target_molecule_id=target_id,
            reason=MergeReason.DISCLOSURE_RESOLVED,
            merged_by=user_id,
            snapshot=snapshot,
            disclosure_request_id=disc_id,
            notes="Merged via disclosure workflow",
        )

        assert event.disclosure_request_id == disc_id
        assert event.notes == "Merged via disclosure workflow"
        assert event.reason == MergeReason.DISCLOSURE_RESOLVED

    def test_self_merge_raises(
        self,
        user_id: uuid.UUID,
        snapshot: dict,
    ) -> None:
        same_id = uuid.uuid4()
        with pytest.raises(ValidationError, match="cannot merge into itself"):
            MergeEvent.create(
                source_molecule_id=same_id,
                target_molecule_id=same_id,
                reason=MergeReason.DUPLICATE_CLEANUP,
                merged_by=user_id,
                snapshot=snapshot,
            )

    def test_empty_snapshot_ok(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        event = MergeEvent.create(
            source_molecule_id=source_id,
            target_molecule_id=target_id,
            reason=MergeReason.STRUCTURE_CORRECTION,
            merged_by=user_id,
            snapshot={},
        )

        assert event.snapshot == {}

    def test_has_expected_attributes(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot: dict,
    ) -> None:
        event = MergeEvent.create(
            source_molecule_id=source_id,
            target_molecule_id=target_id,
            reason=MergeReason.MANUAL_MERGE,
            merged_by=user_id,
            snapshot=snapshot,
        )

        assert event.id is not None
        assert event.created_at is not None
