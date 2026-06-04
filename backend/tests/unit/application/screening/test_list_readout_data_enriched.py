"""Unit tests for ListReadoutDataEnriched — molecule/batch name + structure enrichment."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self

import pytest

from cellar.application.screening.list_readout_data_enriched import (
    ListReadoutDataEnriched,
    ListReadoutDataEnrichedQuery,
)
from cellar.application.screening.readout_data_enriched_reader import MoleculeDisplayRow

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeUoW:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


@dataclass
class _FakeReadout:
    molecule_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None


@dataclass
class _FakeRepo:
    rows: list[_FakeReadout]

    async def find_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> list[_FakeReadout]:
        return self.rows


@dataclass
class _FakeReader:
    molecules: dict[uuid.UUID, MoleculeDisplayRow]
    batches: dict[uuid.UUID, str] = field(default_factory=dict)

    async def resolve_molecules(
        self, workspace_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MoleculeDisplayRow]:
        return {mid: self.molecules[mid] for mid in molecule_ids if mid in self.molecules}

    async def resolve_batch_numbers(
        self, workspace_id: uuid.UUID, batch_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        return {bid: self.batches[bid] for bid in batch_ids if bid in self.batches}

    async def resolve_molecule_registration_numbers(
        self, workspace_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:  # pragma: no cover - part of protocol, unused here
        return {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enriches_readout_rows_with_molecule_smiles() -> None:
    """The enriched row carries the molecule's SMILES (for inline structures)."""
    ws = uuid.uuid4()
    mol_id = uuid.uuid4()
    reader = _FakeReader(
        molecules={
            mol_id: MoleculeDisplayRow(
                registration_number="CV-00001",
                name="Compound A",
                synonyms=["ASA"],
                smiles="CC(=O)Oc1ccccc1C(=O)O",
            )
        }
    )
    uc = ListReadoutDataEnriched(_FakeUoW(), _FakeRepo([_FakeReadout(molecule_id=mol_id)]), reader)

    enriched = (
        await uc(ListReadoutDataEnrichedQuery(workspace_id=ws, run_id=uuid.uuid4()), auth=None)
    ).unwrap()

    assert len(enriched) == 1
    assert enriched[0].smiles == "CC(=O)Oc1ccccc1C(=O)O"
    assert enriched[0].registration_number == "CV-00001"


@pytest.mark.asyncio
async def test_smiles_is_none_when_molecule_unresolved() -> None:
    """A row whose molecule doesn't resolve gets smiles=None, not an error."""
    ws = uuid.uuid4()
    reader = _FakeReader(molecules={})
    uc = ListReadoutDataEnriched(
        _FakeUoW(), _FakeRepo([_FakeReadout(molecule_id=uuid.uuid4())]), reader
    )

    enriched = (
        await uc(ListReadoutDataEnrichedQuery(workspace_id=ws, run_id=uuid.uuid4()), auth=None)
    ).unwrap()

    assert enriched[0].smiles is None
