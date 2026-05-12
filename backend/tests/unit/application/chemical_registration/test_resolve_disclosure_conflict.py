"""Tests for ResolveDisclosureConflict command use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Result, Success

from cellar.application.chemical_registration.protocols import (
    ProcessedStructureDTO,
    QCResultDTO,
)
from cellar.application.chemical_registration.resolve_disclosure_conflict import (
    ResolveConflictCommand,
    ResolveDisclosureConflict,
)
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.enums import (
    DisclosureStatus,
    MoleculeType,
    Stereochemistry,
)
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

_STRUCTURE = ChemicalStructure(
    smiles="c1ccccc1",
    cxsmiles="c1ccccc1",
    inchi="InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H",
    inchi_key="UHOVQNZJYSORNB-UHFFFAOYSA-N",
    molfile="fake",
)

_DESCRIPTORS = ComputedDescriptors(
    molecular_formula="C6H6",
    molecular_weight=78.11,
    exact_mass=78.047,
    logp=1.56,
    tpsa=0.0,
    hbd=0,
    hba=0,
    rotatable_bonds=0,
    aromatic_rings=1,
    ring_count=1,
    heavy_atom_count=6,
    ro5_violations=0,
)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.committed = False
        self._session = AsyncMock()

    @property
    def session(self) -> AsyncMock:
        return self._session

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
    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)


class FakeDisclosureRepo:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, DisclosureRequest] = {}

    def add(self, dr: DisclosureRequest) -> None:
        self._store[dr.id] = dr

    async def find_by_id(self, id: uuid.UUID) -> DisclosureRequest | None:
        return self._store.get(id)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> DisclosureRequest | None:
        entity = self._store.get(id)
        if entity is not None and entity.workspace_id != workspace_id:
            return None
        return entity

    async def save(self, aggregate: DisclosureRequest) -> None:
        self._store[aggregate.id] = aggregate


class FakeMoleculeRepo:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Molecule] = {}

    def add(self, mol: Molecule) -> None:
        self._store[mol.id] = mol

    async def find_by_id(self, id: uuid.UUID) -> Molecule | None:
        return self._store.get(id)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Molecule | None:
        entity = self._store.get(id)
        if entity is not None and entity.workspace_id != workspace_id:
            return None
        return entity

    async def find_by_inchi_key(
        self, workspace_id: uuid.UUID, inchi_key: str
    ) -> Molecule | None:
        for m in self._store.values():
            if (
                m.workspace_id == workspace_id
                and m.structure
                and m.structure.inchi_key == inchi_key
            ):
                return m
        return None

    async def save(self, aggregate: Molecule) -> None:
        self._store[aggregate.id] = aggregate


class FakeStructureProcessor:
    def process(
        self, raw_smiles: str, *, qc_reject_threshold: int | None = None
    ) -> Result[ProcessedStructureDTO, DomainError]:
        return Success(
            ProcessedStructureDTO(
                structure=_STRUCTURE,
                descriptors=_DESCRIPTORS,
                fingerprints={},
                qc_result=QCResultDTO(total_penalty=0, issues=[]),
                stereochemistry=Stereochemistry.ACHIRAL,
            )
        )


def _make_conflict_dr(molecule_id: uuid.UUID) -> DisclosureRequest:
    """Create a DisclosureRequest in CONFLICT state."""
    dr = DisclosureRequest.create(
        workspace_id=WS_ID,
        molecule_id=molecule_id,
        disclosed_smiles="c1ccccc1",
        requested_by=USER_ID,
    )
    dr.start_processing()
    dr.mark_conflict(reason="CAS mismatch")
    dr.clear_events()
    return dr


def _make_undisclosed_mol() -> Molecule:
    mol = Molecule.register_undisclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CV-00099"),
        name="Undisclosed compound",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=ORG_ID,
    )
    mol.clear_events()
    return mol


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolveReject:
    @pytest.mark.asyncio
    async def test_reject_transitions_to_rejected(self) -> None:
        uow = FakeUnitOfWork()
        disclosure_repo = FakeDisclosureRepo()
        mol_repo = FakeMoleculeRepo()
        dispatcher = FakeEventDispatcher()

        mol = _make_undisclosed_mol()
        mol_repo.add(mol)
        dr = _make_conflict_dr(mol.id)
        disclosure_repo.add(dr)

        uc = ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=disclosure_repo,
            molecule_repo=mol_repo,
            merge_service=AsyncMock(),
            structure_processor=FakeStructureProcessor(),
            dispatcher=dispatcher,
        )

        result = await uc(
            ResolveConflictCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                resolution="reject",
                reason="Bad data",
                resolved_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Success)
        resolved = result.unwrap()
        assert resolved.status == DisclosureStatus.REJECTED


class TestResolveAcceptAsNew:
    @pytest.mark.asyncio
    async def test_accept_as_new_discloses_molecule(self) -> None:
        uow = FakeUnitOfWork()
        disclosure_repo = FakeDisclosureRepo()
        mol_repo = FakeMoleculeRepo()
        dispatcher = FakeEventDispatcher()

        mol = _make_undisclosed_mol()
        mol_repo.add(mol)
        dr = _make_conflict_dr(mol.id)
        disclosure_repo.add(dr)

        uc = ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=disclosure_repo,
            molecule_repo=mol_repo,
            merge_service=AsyncMock(),
            structure_processor=FakeStructureProcessor(),
            dispatcher=dispatcher,
        )

        result = await uc(
            ResolveConflictCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                resolution="accept_as_new",
                resolved_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Success)
        resolved = result.unwrap()
        assert resolved.status == DisclosureStatus.DISCLOSED

        # Molecule should now be disclosed
        saved_mol = await mol_repo.find_by_id(mol.id)
        assert saved_mol is not None
        assert saved_mol.structure is not None


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_resolution(self) -> None:
        uow = FakeUnitOfWork()
        uc = ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=FakeDisclosureRepo(),
            molecule_repo=FakeMoleculeRepo(),
            merge_service=AsyncMock(),
            structure_processor=FakeStructureProcessor(),
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            ResolveConflictCommand(
                workspace_id=WS_ID,
                disclosure_id=uuid.uuid4(),
                resolution="invalid",
                resolved_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_disclosure_not_found(self) -> None:
        uow = FakeUnitOfWork()
        uc = ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=FakeDisclosureRepo(),
            molecule_repo=FakeMoleculeRepo(),
            merge_service=AsyncMock(),
            structure_processor=FakeStructureProcessor(),
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            ResolveConflictCommand(
                workspace_id=WS_ID,
                disclosure_id=uuid.uuid4(),
                resolution="reject",
                resolved_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_not_in_conflict_state(self) -> None:
        uow = FakeUnitOfWork()
        disclosure_repo = FakeDisclosureRepo()
        mol_repo = FakeMoleculeRepo()

        mol = _make_undisclosed_mol()
        mol_repo.add(mol)

        # Create a DR in PENDING state (not CONFLICT)
        dr = DisclosureRequest.create(
            workspace_id=WS_ID,
            molecule_id=mol.id,
            disclosed_smiles="c1ccccc1",
            requested_by=USER_ID,
        )
        dr.clear_events()
        disclosure_repo.add(dr)

        uc = ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=disclosure_repo,
            molecule_repo=mol_repo,
            merge_service=AsyncMock(),
            structure_processor=FakeStructureProcessor(),
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            ResolveConflictCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                resolution="reject",
                resolved_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
