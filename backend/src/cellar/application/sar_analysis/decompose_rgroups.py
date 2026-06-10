"""Decompose a set of molecules against a core into R-group columns."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from cellar.application.sar_analysis.build_scaffold_network import (
    MoleculeFetcherForScaffoldTree,
)
from cellar.application.sar_analysis.rgroup_decomposition import RGroupDecomposer
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult


@dataclass(frozen=True)
class DecomposeRGroupsInput:
    molecule_ids: list[UUID]
    workspace_id: UUID
    core_smiles: str


class DecomposeRGroups:
    """Fetch the set's (id, smiles), then decompose against the given core."""

    def __init__(
        self,
        *,
        molecule_fetcher: MoleculeFetcherForScaffoldTree,
        decomposer: RGroupDecomposer,
        uow: UnitOfWork,
    ) -> None:
        self._fetcher = molecule_fetcher
        self._decomposer = decomposer
        self._uow = uow

    async def execute(self, payload: DecomposeRGroupsInput) -> RGroupDecompositionResult:
        async with self._uow:
            rows = await self._fetcher.fetch_for_scaffold_tree(
                molecule_ids=payload.molecule_ids, workspace_id=payload.workspace_id
            )
        molecules = [(mid, smiles) for (mid, smiles, _bms) in rows]
        return self._decomposer.decompose(core_smiles=payload.core_smiles, molecules=molecules)
