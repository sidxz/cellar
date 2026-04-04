"""Tests for MergeService — molecule merge orchestration."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.merge_service import (
    MergeCommand,
    MergeService,
    _build_snapshot,
)
from chem_vault.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from chem_vault.domain.chemical_registration.enums import (
    IdentifierType,
    MergeReason,
    MoleculeType,
)
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from chem_vault.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)
from tests.fakes.fake_auth import FakeAuth


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeMoleculeRepository:
    """In-memory molecule store for unit tests."""

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Molecule] = {}

    def add(self, mol: Molecule) -> None:
        """Test helper: seed the store."""
        self._store[mol.id] = mol

    async def find_by_id(self, id: uuid.UUID) -> Molecule | None:
        return self._store.get(id)

    async def save(self, aggregate: Molecule) -> None:
        self._store[aggregate.id] = aggregate


class FakeMergeEventRepository:
    """In-memory merge-event store for unit tests."""

    def __init__(self) -> None:
        self.saved: list[MergeEvent] = []

    async def save(self, entity: MergeEvent) -> None:
        self.saved.append(entity)


class FakeUnitOfWork:
    """Minimal UoW that tracks commit/rollback calls."""

    def __init__(self) -> None:
        self.committed = False
        self._session = AsyncMock()

    @property
    def session(self) -> AsyncMock:
        return self._session

    def track(self, aggregate: object) -> None:
        pass

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class FakeEventDispatcher:
    """Captures dispatched events for assertions."""

    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)


# ---------------------------------------------------------------------------
# Molecule helpers
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _make_source() -> Molecule:
    mol = Molecule.register_undisclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CV-00001"),
        name="Source compound",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=ORG_ID,
    )
    mol.clear_events()
    return mol


def _make_target() -> Molecule:
    mol = Molecule.register_disclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CV-00002"),
        name="Target compound",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        structure=ChemicalStructure(
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            cxsmiles="CC(=O)Oc1ccccc1C(=O)O",
            inchi="InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
            inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            molfile="fake",
        ),
        descriptors=ComputedDescriptors(
            molecular_formula="C9H8O4",
            molecular_weight=180.16,
            exact_mass=180.042,
            logp=1.31,
            tpsa=63.60,
            hbd=1,
            hba=4,
            rotatable_bonds=3,
            aromatic_rings=1,
            ring_count=1,
            heavy_atom_count=13,
            ro5_violations=0,
        ),
        originating_org_id=ORG_ID,
    )
    mol.clear_events()
    return mol


def _make_command(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    reason: MergeReason = MergeReason.MANUAL_MERGE,
) -> MergeCommand:
    return MergeCommand(
        source_molecule_id=source_id,
        target_molecule_id=target_id,
        reason=reason,
        merged_by=USER_ID,
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def _deps():
    """Return all wired dependencies as a dict for MergeService."""
    uow = FakeUnitOfWork()
    mol_repo = FakeMoleculeRepository()
    merge_repo = FakeMergeEventRepository()
    dispatcher = FakeEventDispatcher()
    registry = MergeSideEffectRegistry()

    service = MergeService(
        uow=uow,
        molecule_repo=mol_repo,
        merge_event_repo=merge_repo,
        dispatcher=dispatcher,
        side_effect_registry=registry,
    )
    return {
        "service": service,
        "uow": uow,
        "mol_repo": mol_repo,
        "merge_repo": merge_repo,
        "dispatcher": dispatcher,
        "registry": registry,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMergeServiceSuccess:
    @pytest.mark.asyncio
    async def test_merge_success(self, _deps: dict) -> None:
        """Happy path: source becomes tombstone, merge event persisted, UoW committed."""
        source = _make_source()
        target = _make_target()
        _deps["mol_repo"].add(source)
        _deps["mol_repo"].add(target)

        cmd = _make_command(source.id, target.id)
        result = await _deps["service"](cmd, auth=FakeAuth())

        assert isinstance(result, Success)
        merge_event = result.unwrap()
        assert isinstance(merge_event, MergeEvent)
        assert merge_event.source_molecule_id == source.id
        assert merge_event.target_molecule_id == target.id
        assert merge_event.reason == MergeReason.MANUAL_MERGE

        # Source is now a tombstone
        saved_source = await _deps["mol_repo"].find_by_id(source.id)
        assert saved_source is not None
        assert saved_source.is_tombstone
        assert saved_source.merged_into_id == target.id

        # MergeEvent was persisted
        assert len(_deps["merge_repo"].saved) == 1

        # UoW was committed
        assert _deps["uow"].committed

    @pytest.mark.asyncio
    async def test_merge_transfers_registration_number_as_identifier(
        self, _deps: dict
    ) -> None:
        """Target gains source's registration number as INTERNAL_LEGACY identifier."""
        source = _make_source()
        target = _make_target()
        _deps["mol_repo"].add(source)
        _deps["mol_repo"].add(target)

        cmd = _make_command(source.id, target.id)
        await _deps["service"](cmd, auth=FakeAuth())

        saved_target = await _deps["mol_repo"].find_by_id(target.id)
        assert saved_target is not None
        legacy_ids = [
            i
            for i in saved_target.identifiers
            if i.identifier_type == IdentifierType.INTERNAL_LEGACY
        ]
        assert len(legacy_ids) == 1
        assert legacy_ids[0].identifier == "CV-00001"
        assert legacy_ids[0].source == "Merge from CV-00001"

    @pytest.mark.asyncio
    async def test_merge_does_not_duplicate_identifier(self, _deps: dict) -> None:
        """If target already has source's reg number, no duplicate is added."""
        source = _make_source()
        target = _make_target()
        # Pre-seed target with the identifier
        target.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=target.id,
                identifier="CV-00001",
                identifier_type=IdentifierType.INTERNAL_LEGACY,
                source="Previous merge",
                registered_by=USER_ID,
            )
        )
        _deps["mol_repo"].add(source)
        _deps["mol_repo"].add(target)

        cmd = _make_command(source.id, target.id)
        await _deps["service"](cmd, auth=FakeAuth())

        saved_target = await _deps["mol_repo"].find_by_id(target.id)
        assert saved_target is not None
        legacy_ids = [
            i for i in saved_target.identifiers if i.identifier == "CV-00001"
        ]
        # Should still be just the one that was there before
        assert len(legacy_ids) == 1


class TestMergeServiceFailures:
    @pytest.mark.asyncio
    async def test_merge_source_not_found(self, _deps: dict) -> None:
        target = _make_target()
        _deps["mol_repo"].add(target)

        cmd = _make_command(uuid.uuid4(), target.id)
        result = await _deps["service"](cmd, auth=FakeAuth())

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, NotFoundError)

    @pytest.mark.asyncio
    async def test_merge_target_not_found(self, _deps: dict) -> None:
        source = _make_source()
        _deps["mol_repo"].add(source)

        cmd = _make_command(source.id, uuid.uuid4())
        result = await _deps["service"](cmd, auth=FakeAuth())

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, NotFoundError)

    @pytest.mark.asyncio
    async def test_merge_source_already_tombstone(self, _deps: dict) -> None:
        source = _make_source()
        target = _make_target()
        # Make source a tombstone via a prior merge
        other_target = _make_target()
        source.mark_as_tombstone(
            merged_into_id=other_target.id,
            merge_event_id=uuid.uuid4(),
            reason="prior merge",
        )
        source.clear_events()

        _deps["mol_repo"].add(source)
        _deps["mol_repo"].add(target)

        cmd = _make_command(source.id, target.id)
        result = await _deps["service"](cmd, auth=FakeAuth())

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ConflictError)
        assert "tombstone" in err.message.lower()

    @pytest.mark.asyncio
    async def test_merge_target_already_tombstone(self, _deps: dict) -> None:
        source = _make_source()
        target = _make_target()
        # Make target a tombstone
        other_target = _make_target()
        target.mark_as_tombstone(
            merged_into_id=other_target.id,
            merge_event_id=uuid.uuid4(),
            reason="prior merge",
        )
        target.clear_events()

        _deps["mol_repo"].add(source)
        _deps["mol_repo"].add(target)

        cmd = _make_command(source.id, target.id)
        result = await _deps["service"](cmd, auth=FakeAuth())

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ConflictError)
        assert "tombstone" in err.message.lower()

    @pytest.mark.asyncio
    async def test_merge_self_raises(self, _deps: dict) -> None:
        mol = _make_source()
        _deps["mol_repo"].add(mol)

        cmd = _make_command(mol.id, mol.id)
        result = await _deps["service"](cmd, auth=FakeAuth())

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "itself" in err.message.lower()


class TestMergeServiceSideEffects:
    @pytest.mark.asyncio
    async def test_side_effect_registry_invoked(self, _deps: dict) -> None:
        """A registered side-effect handler is called with session + IDs."""
        source = _make_source()
        target = _make_target()
        _deps["mol_repo"].add(source)
        _deps["mol_repo"].add(target)

        handler = AsyncMock()
        _deps["registry"].register(handler)

        cmd = _make_command(source.id, target.id)
        await _deps["service"](cmd, auth=FakeAuth())

        handler.on_merge.assert_awaited_once_with(
            _deps["uow"].session,
            source.id,
            target.id,
        )


class TestMergeSnapshot:
    @pytest.mark.asyncio
    async def test_merge_snapshot_contains_registration_number(
        self, _deps: dict
    ) -> None:
        """The snapshot dict persisted in MergeEvent captures source state."""
        source = _make_source()
        target = _make_target()
        _deps["mol_repo"].add(source)
        _deps["mol_repo"].add(target)

        cmd = _make_command(source.id, target.id)
        result = await _deps["service"](cmd, auth=FakeAuth())

        merge_event = result.unwrap()
        snap = merge_event.snapshot
        assert snap["registration_number"] == "CV-00001"
        assert snap["name"] == "Source compound"
        assert snap["molecule_type"] == "small_molecule"
        assert snap["structure_status"] == "undisclosed"
        assert isinstance(snap["identifiers"], list)
        assert isinstance(snap["tags"], list)

    def test_build_snapshot_helper(self) -> None:
        """Direct test of _build_snapshot utility."""
        mol = _make_source()
        mol.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol.id,
                identifier="CAS-123",
                identifier_type=IdentifierType.CAS_NUMBER,
                source="vendor",
                registered_by=USER_ID,
            )
        )
        snap = _build_snapshot(mol)
        assert snap["registration_number"] == "CV-00001"
        assert snap["identifiers"] == [
            {"identifier": "CAS-123", "type": "cas_number"}
        ]
        assert snap["tags"] == []
