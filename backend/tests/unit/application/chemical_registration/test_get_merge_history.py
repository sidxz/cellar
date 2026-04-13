"""Tests for GetMergeHistory query use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.get_merge_history import (
    GetMergeHistory,
    GetMergeHistoryQuery,
)
from chem_vault.domain.chemical_registration.enums import MergeReason, MoleculeType
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.shared.errors import NotFoundError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import RegistrationNumber

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class FakeUnitOfWork:
    async def commit(self) -> list[DomainEvent]:
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


class FakeMergeEventRepo:
    def __init__(self) -> None:
        self._store: list[MergeEvent] = []

    def add(self, event: MergeEvent) -> None:
        self._store.append(event)

    async def find_by_molecule(self, workspace_id: uuid.UUID, molecule_id: uuid.UUID) -> list[MergeEvent]:
        return [
            e
            for e in self._store
            if e.workspace_id == workspace_id
            and (e.source_molecule_id == molecule_id
                 or e.target_molecule_id == molecule_id)
        ]


def _make_mol(name: str = "Test") -> Molecule:
    mol = Molecule.register_undisclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value=f"CV-{uuid.uuid4().hex[:5]}"),
        name=name,
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=ORG_ID,
    )
    mol.clear_events()
    return mol


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetMergeHistory:
    @pytest.mark.asyncio
    async def test_returns_events_as_source(self) -> None:
        mol_repo = FakeMoleculeRepo()
        merge_repo = FakeMergeEventRepo()

        mol = _make_mol("Source")
        target = _make_mol("Target")
        mol_repo.add(mol)
        mol_repo.add(target)

        event = MergeEvent.create(
            workspace_id=WS_ID,
            source_molecule_id=mol.id,
            target_molecule_id=target.id,
            reason=MergeReason.MANUAL_MERGE,
            merged_by=USER_ID,
            snapshot={"registration_number": "CV-00001"},
        )
        merge_repo.add(event)

        uc = GetMergeHistory(FakeUnitOfWork(), mol_repo, merge_repo)
        result = await uc(
            GetMergeHistoryQuery(workspace_id=WS_ID, molecule_id=mol.id)
        )

        assert isinstance(result, Success)
        events = result.unwrap()
        assert len(events) == 1
        assert events[0].source_molecule_id == mol.id

    @pytest.mark.asyncio
    async def test_returns_events_as_target(self) -> None:
        mol_repo = FakeMoleculeRepo()
        merge_repo = FakeMergeEventRepo()

        source = _make_mol("Source")
        target = _make_mol("Target")
        mol_repo.add(source)
        mol_repo.add(target)

        event = MergeEvent.create(
            workspace_id=WS_ID,
            source_molecule_id=source.id,
            target_molecule_id=target.id,
            reason=MergeReason.DISCLOSURE_RESOLVED,
            merged_by=USER_ID,
            snapshot={},
        )
        merge_repo.add(event)

        uc = GetMergeHistory(FakeUnitOfWork(), mol_repo, merge_repo)
        result = await uc(
            GetMergeHistoryQuery(workspace_id=WS_ID, molecule_id=target.id)
        )

        assert isinstance(result, Success)
        assert len(result.unwrap()) == 1

    @pytest.mark.asyncio
    async def test_empty_history(self) -> None:
        mol_repo = FakeMoleculeRepo()
        merge_repo = FakeMergeEventRepo()
        mol = _make_mol()
        mol_repo.add(mol)

        uc = GetMergeHistory(FakeUnitOfWork(), mol_repo, merge_repo)
        result = await uc(
            GetMergeHistoryQuery(workspace_id=WS_ID, molecule_id=mol.id)
        )

        assert isinstance(result, Success)
        assert result.unwrap() == []

    @pytest.mark.asyncio
    async def test_molecule_not_found(self) -> None:
        mol_repo = FakeMoleculeRepo()
        merge_repo = FakeMergeEventRepo()

        uc = GetMergeHistory(FakeUnitOfWork(), mol_repo, merge_repo)
        result = await uc(
            GetMergeHistoryQuery(workspace_id=WS_ID, molecule_id=uuid.uuid4())
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
