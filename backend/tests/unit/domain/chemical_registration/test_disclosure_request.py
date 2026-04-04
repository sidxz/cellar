"""Tests for DisclosureRequest aggregate root."""

import uuid

import pytest

from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.enums import (
    DisclosureResolutionType,
    DisclosureStatus,
)
from chem_vault.domain.chemical_registration.events import (
    DisclosureConflict,
    DisclosureRequested,
    DisclosureResolved,
)
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def molecule_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def bulk_id() -> uuid.UUID:
    return uuid.uuid4()


def _make(
    molecule_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    disclosing_org_id: uuid.UUID | None = None,
    bulk_disclosure_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> DisclosureRequest:
    """Create a DisclosureRequest and clear creation events for transition tests."""
    req = DisclosureRequest.create(
        molecule_id=molecule_id,
        disclosed_smiles="CCO",
        requested_by=user_id,
        disclosing_org_id=disclosing_org_id,
        bulk_disclosure_id=bulk_disclosure_id,
        notes=notes,
    )
    req.clear_events()
    return req


# ---------------------------------------------------------------------------
# TestDisclosureRequestCreation
# ---------------------------------------------------------------------------


class TestDisclosureRequestCreation:
    def test_create_sets_all_fields(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        req = DisclosureRequest.create(
            molecule_id=molecule_id,
            disclosed_smiles="CCO",
            requested_by=user_id,
            disclosing_org_id=org_id,
        )

        assert req.molecule_id == molecule_id
        assert req.disclosed_smiles == "CCO"
        assert req.requested_by == user_id
        assert req.disclosing_org_id == org_id
        assert req.status == DisclosureStatus.PENDING
        assert req.canonical_smiles is None
        assert req.inchi_key is None
        assert req.resolution_type is None
        assert req.resolved_to_molecule_id is None
        assert req.bulk_disclosure_id is None
        assert req.resolved_at is None
        assert req.conflict_reason is None
        assert req.notes is None
        assert req.version == 1

    def test_create_emits_disclosure_requested_event(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        req = DisclosureRequest.create(
            molecule_id=molecule_id,
            disclosed_smiles="CCO",
            requested_by=user_id,
            disclosing_org_id=org_id,
        )
        events = req.collect_events()

        assert len(events) == 1
        assert isinstance(events[0], DisclosureRequested)
        assert events[0].aggregate_id == req.id
        assert events[0].aggregate_type == "DisclosureRequest"
        assert events[0].molecule_id == molecule_id
        assert events[0].disclosing_org_id == org_id

    def test_create_with_bulk_parent(
        self,
        molecule_id: uuid.UUID,
        user_id: uuid.UUID,
        bulk_id: uuid.UUID,
    ) -> None:
        req = DisclosureRequest.create(
            molecule_id=molecule_id,
            disclosed_smiles="CCO",
            requested_by=user_id,
            bulk_disclosure_id=bulk_id,
            notes="Bulk upload batch 7",
        )

        assert req.bulk_disclosure_id == bulk_id
        assert req.notes == "Bulk upload batch 7"

    def test_create_with_empty_smiles_raises(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="disclosed_smiles must not be empty"):
            DisclosureRequest.create(
                molecule_id=molecule_id,
                disclosed_smiles="",
                requested_by=user_id,
            )

    def test_create_with_whitespace_smiles_raises(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="disclosed_smiles must not be empty"):
            DisclosureRequest.create(
                molecule_id=molecule_id,
                disclosed_smiles="   ",
                requested_by=user_id,
            )

    def test_smiles_is_stripped(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = DisclosureRequest.create(
            molecule_id=molecule_id,
            disclosed_smiles="  CCO  ",
            requested_by=user_id,
        )
        assert req.disclosed_smiles == "CCO"


# ---------------------------------------------------------------------------
# TestDisclosureRequestTransitions
# ---------------------------------------------------------------------------


class TestDisclosureRequestTransitions:
    def test_start_processing(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        req.start_processing()

        assert req.status == DisclosureStatus.PROCESSING

    def test_resolve_as_new_structure(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        req.start_processing()
        req.clear_events()

        req.resolve_as_new_structure(
            canonical_smiles="CCO",
            inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        )

        assert req.status == DisclosureStatus.DISCLOSED
        assert req.canonical_smiles == "CCO"
        assert req.inchi_key == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        assert req.resolution_type == DisclosureResolutionType.NEW_STRUCTURE
        assert req.resolved_at is not None

        events = req.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], DisclosureResolved)
        assert events[0].resolution_type == "new_structure"
        assert events[0].resolved_to_molecule_id is None

    def test_resolve_as_merged(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        target_mol_id = uuid.uuid4()
        req = _make(molecule_id, user_id)
        req.start_processing()
        req.clear_events()

        req.resolve_as_merged(
            canonical_smiles="CCO",
            inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            resolved_to_molecule_id=target_mol_id,
        )

        assert req.status == DisclosureStatus.MERGED
        assert req.resolution_type == DisclosureResolutionType.MERGED_INTO_EXISTING
        assert req.resolved_to_molecule_id == target_mol_id
        assert req.resolved_at is not None

        events = req.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], DisclosureResolved)
        assert events[0].resolution_type == "merged_into_existing"
        assert events[0].resolved_to_molecule_id == target_mol_id

    def test_mark_conflict(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        req.start_processing()
        req.clear_events()

        req.mark_conflict(reason="Multiple InChIKey matches found")

        assert req.status == DisclosureStatus.CONFLICT
        assert req.conflict_reason == "Multiple InChIKey matches found"

        events = req.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], DisclosureConflict)
        assert events[0].conflict_reason == "Multiple InChIKey matches found"

    def test_reject_from_pending(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)

        req.reject(reason="Invalid SMILES notation")

        assert req.status == DisclosureStatus.REJECTED
        assert req.conflict_reason == "Invalid SMILES notation"
        assert req.resolved_at is not None

    def test_reject_from_conflict(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        req.start_processing()
        req.mark_conflict(reason="Ambiguous match")
        req.clear_events()

        req.reject(reason="Admin rejected after review")

        assert req.status == DisclosureStatus.REJECTED
        assert req.conflict_reason == "Admin rejected after review"
        assert req.resolved_at is not None

    def test_cannot_start_processing_from_disclosed(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        req.start_processing()
        req.resolve_as_new_structure(
            canonical_smiles="CCO",
            inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        )

        with pytest.raises(ValidationError, match="Cannot transition disclosure status"):
            req.start_processing()

    def test_cannot_resolve_from_pending(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)

        with pytest.raises(ValidationError, match="Cannot transition disclosure status"):
            req.resolve_as_new_structure(
                canonical_smiles="CCO",
                inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            )

    def test_cannot_reject_from_processing(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        req.start_processing()

        with pytest.raises(ValidationError, match="Cannot transition disclosure status"):
            req.reject(reason="Nope")

    def test_cannot_reject_from_merged(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        req.start_processing()
        req.resolve_as_merged(
            canonical_smiles="CCO",
            inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            resolved_to_molecule_id=uuid.uuid4(),
        )

        with pytest.raises(ValidationError, match="Cannot transition disclosure status"):
            req.reject(reason="Too late")

    def test_transitions_update_updated_at(
        self, molecule_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        req = _make(molecule_id, user_id)
        initial_updated = req.updated_at

        req.start_processing()
        assert req.updated_at >= initial_updated

        after_processing = req.updated_at
        req.resolve_as_new_structure(
            canonical_smiles="CCO",
            inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        )
        assert req.updated_at >= after_processing
