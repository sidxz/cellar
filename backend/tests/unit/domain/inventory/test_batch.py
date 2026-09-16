"""Tests for Batch aggregate root."""

import uuid

import pytest

from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.inventory.events import BatchCreated, BatchReassigned
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Amount, BatchNumber


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def molecule_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def chemist_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_batch(
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID,
    chemist_id: uuid.UUID,
    **kwargs,
) -> Batch:
    defaults = dict(
        workspace_id=workspace_id,
        molecule_id=molecule_id,
        batch_number=BatchNumber(value="CV-00001-001"),
        amount=Amount(value=100.0, unit=AmountUnit.MG),
        source=BatchSource.SYNTHESIZED,
        chemist=chemist_id,
    )
    defaults.update(kwargs)
    return Batch.create(**defaults)


class TestBatchCreation:
    def test_create_sets_all_fields(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id)

        assert batch.workspace_id == workspace_id
        assert batch.molecule_id == molecule_id
        assert batch.batch_number.value == "CV-00001-001"
        assert batch.amount.value == 100.0
        assert batch.source == BatchSource.SYNTHESIZED
        assert batch.chemist == chemist_id
        assert batch.purity is None
        assert batch.version == 1

    def test_create_emits_batch_created_event(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id)
        events = batch.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, BatchCreated)
        assert evt.molecule_id == molecule_id
        assert evt.batch_number == "CV-00001-001"
        assert evt.source == "synthesized"


    def test_purity_zero_raises(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="Purity"):
            _make_batch(workspace_id, molecule_id, chemist_id, purity=0)

    def test_purity_over_100_raises(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="Purity"):
            _make_batch(workspace_id, molecule_id, chemist_id, purity=100.1)

    def test_purity_negative_raises(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="Purity"):
            _make_batch(workspace_id, molecule_id, chemist_id, purity=-1)

    def test_purity_100_is_valid(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id, purity=100)
        assert batch.purity == 100

    def test_all_batch_sources(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        for source in BatchSource:
            batch = _make_batch(workspace_id, molecule_id, chemist_id, source=source)
            assert batch.source == source

    def test_batch_number_is_immutable(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id)
        assert batch.batch_number.value == "CV-00001-001"
        # batch_number property is read-only (no setter)
        with pytest.raises(AttributeError):
            batch.batch_number = BatchNumber(value="new")  # type: ignore[misc]


class TestBatchMerge:
    def test_reassign_to_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id)
        batch.clear_events()

        new_mol = uuid.uuid4()
        merge_evt = uuid.uuid4()
        batch.reassign_to_molecule(new_molecule_id=new_mol, merge_event_id=merge_evt)

        assert batch.molecule_id == new_mol
        events = batch.collect_events()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, BatchReassigned)
        assert evt.old_molecule_id == molecule_id
        assert evt.new_molecule_id == new_mol
        assert evt.merge_event_id == merge_evt


class TestBatchUpdates:
    def test_update_amount(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id)
        new_amount = Amount(value=50.0, unit=AmountUnit.MG)
        batch.update_amount(new_amount)
        assert batch.amount.value == 50.0

    def test_update_purity(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id)
        batch.update_purity(95.0)
        assert batch.purity == 95.0

    def test_update_purity_invalid_raises(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        batch = _make_batch(workspace_id, molecule_id, chemist_id)
        with pytest.raises(ValidationError, match="Purity"):
            batch.update_purity(0)


def test_external_reference_source_exists() -> None:
    """Auto-created placeholder batches use this source."""
    assert BatchSource.EXTERNAL_REFERENCE.value == "external_reference"


# ---------------------------------------------------------------------------
# BatchIdentifier collection on Batch
# ---------------------------------------------------------------------------

from cellar.domain.inventory.batch_identifier import BatchIdentifier  # noqa: E402


class TestBatchIdentifiers:
    def test_new_batch_has_empty_identifiers(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        b = _make_batch(workspace_id, molecule_id, chemist_id)
        assert b.identifiers == []

    def test_add_identifier_appends(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        b = _make_batch(workspace_id, molecule_id, chemist_id)
        ident = BatchIdentifier.create(
            batch_id=b.id,
            identifier="SACC-001-A",
            identifier_type="external_lot",
            source="CDD",
            registered_by=uuid.uuid4(),
        )
        b.add_identifier(ident)
        assert len(b.identifiers) == 1
        assert b.identifiers[0].identifier == "SACC-001-A"

    def test_remove_identifier_removes(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        b = _make_batch(workspace_id, molecule_id, chemist_id)
        ident = BatchIdentifier.create(
            batch_id=b.id,
            identifier="ABC",
            identifier_type="custom",
            source="user",
            registered_by=uuid.uuid4(),
        )
        b.add_identifier(ident)
        b.remove_identifier(ident.id)
        assert b.identifiers == []

    def test_remove_identifier_unknown_raises(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        b = _make_batch(workspace_id, molecule_id, chemist_id)
        with pytest.raises(ValidationError, match="not found"):
            b.remove_identifier(uuid.uuid4())

    def test_clear_identifiers(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, chemist_id: uuid.UUID
    ) -> None:
        b = _make_batch(workspace_id, molecule_id, chemist_id)
        for v in ("A", "B", "C"):
            b.add_identifier(
                BatchIdentifier.create(
                    batch_id=b.id,
                    identifier=v,
                    identifier_type="custom",
                    source="user",
                    registered_by=uuid.uuid4(),
                )
            )
        b.clear_identifiers()
        assert b.identifiers == []
