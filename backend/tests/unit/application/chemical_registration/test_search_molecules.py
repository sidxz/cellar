"""Tests for SearchMolecules query use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Any, Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Result, Success

from chem_vault.application.chemical_registration.protocols import (
    ProcessedStructureDTO,
    QCResultDTO,
)
from chem_vault.application.chemical_registration.search_molecules import (
    SearchMolecules,
    SearchMoleculesQuery,
    SimilarityResult,
)
from chem_vault.domain.chemical_registration.enums import MoleculeType
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()


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


def _make_mol(name: str = "Benzene") -> Molecule:
    mol = Molecule.register_disclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CV-00001"),
        name=name,
        molecule_type=MoleculeType.SMALL_MOLECULE,
        structure=_STRUCTURE,
        descriptors=_DESCRIPTORS,
        originating_org_id=ORG_ID,
    )
    mol.clear_events()
    return mol


class FakeMoleculeRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Molecule] = {}

    def add(self, mol: Molecule) -> None:
        self._store[mol.id] = mol

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


class FakeMoleculeReader:
    """Test double for the read-side ``MoleculeReader`` Protocol."""

    def __init__(self, repo: "FakeMoleculeRepository") -> None:
        self._repo = repo

    async def search_substructure(
        self, workspace_id: uuid.UUID, smarts: str
    ) -> list[Molecule]:
        # Simplified fake: return all molecules in workspace
        return [m for m in self._repo._store.values() if m.workspace_id == workspace_id]

    async def search_similarity(
        self, workspace_id: uuid.UUID, smiles: str, threshold: float = 0.7
    ) -> list[tuple[Molecule, float]]:
        return [
            (m, 0.85)
            for m in self._repo._store.values()
            if m.workspace_id == workspace_id
        ]

    async def search_by_query(
        self, workspace_id: uuid.UUID, query: dict, **kwargs
    ) -> list[Molecule]:
        return [m for m in self._repo._store.values() if m.workspace_id == workspace_id]

    async def count_by_query(
        self, workspace_id: uuid.UUID, query: dict, **kwargs
    ) -> int:
        return sum(
            1 for m in self._repo._store.values() if m.workspace_id == workspace_id
        )


class FakeStructureProcessor:
    def __init__(self, *, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def process(
        self, raw_smiles: str, *, qc_reject_threshold: int | None = None
    ) -> Result[ProcessedStructureDTO, DomainError]:
        if self._should_fail:
            return Failure(ValidationError("Bad SMILES"))
        return Success(
            ProcessedStructureDTO(
                structure=_STRUCTURE,
                descriptors=_DESCRIPTORS,
                fingerprints={},
                qc_result=QCResultDTO(total_penalty=0, issues=[]),
            )
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _deps() -> dict[str, Any]:
    uow = FakeUnitOfWork()
    repo = FakeMoleculeRepository()
    reader = FakeMoleculeReader(repo)
    processor = FakeStructureProcessor()
    uc = SearchMolecules(uow, repo, reader, processor)
    return {"uc": uc, "repo": repo, "reader": reader, "processor": processor}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExactSearch:
    @pytest.mark.asyncio
    async def test_exact_search_found(self, _deps: dict) -> None:
        mol = _make_mol()
        _deps["repo"].add(mol)

        query = SearchMoleculesQuery(
            workspace_id=WS_ID, search_type="exact", query="c1ccccc1"
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Success)
        mols = result.unwrap()
        assert len(mols) == 1
        assert mols[0].id == mol.id

    @pytest.mark.asyncio
    async def test_exact_search_not_found(self, _deps: dict) -> None:
        query = SearchMoleculesQuery(
            workspace_id=WS_ID, search_type="exact", query="c1ccccc1"
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Success)
        assert result.unwrap() == []

    @pytest.mark.asyncio
    async def test_exact_search_bad_smiles(self, _deps: dict) -> None:
        _deps["processor"]._should_fail = True
        query = SearchMoleculesQuery(
            workspace_id=WS_ID, search_type="exact", query="NOT_SMILES"
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)


class TestSubstructureSearch:
    @pytest.mark.asyncio
    async def test_substructure_returns_matches(self, _deps: dict) -> None:
        mol = _make_mol()
        _deps["repo"].add(mol)

        query = SearchMoleculesQuery(
            workspace_id=WS_ID, search_type="substructure", query="c1ccccc1"
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Success)
        assert len(result.unwrap()) == 1

    @pytest.mark.asyncio
    async def test_substructure_empty_results(self, _deps: dict) -> None:
        query = SearchMoleculesQuery(
            workspace_id=WS_ID, search_type="substructure", query="c1ccccc1"
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Success)
        assert result.unwrap() == []


class TestSimilaritySearch:
    @pytest.mark.asyncio
    async def test_similarity_returns_scored_results(self, _deps: dict) -> None:
        mol = _make_mol()
        _deps["repo"].add(mol)

        query = SearchMoleculesQuery(
            workspace_id=WS_ID,
            search_type="similarity",
            query="c1ccccc1",
            threshold=0.5,
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Success)
        items = result.unwrap()
        assert len(items) == 1
        assert isinstance(items[0], SimilarityResult)
        assert items[0].molecule.id == mol.id
        assert items[0].similarity == 0.85


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_search_type(self, _deps: dict) -> None:
        query = SearchMoleculesQuery(
            workspace_id=WS_ID, search_type="invalid", query="c1ccccc1"
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_empty_query(self, _deps: dict) -> None:
        query = SearchMoleculesQuery(
            workspace_id=WS_ID, search_type="substructure", query="  "
        )
        result = await _deps["uc"](query)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
