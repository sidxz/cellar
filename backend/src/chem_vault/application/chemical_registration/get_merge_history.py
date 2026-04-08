"""GetMergeHistory query — retrieve merge events for a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
from chem_vault.domain.chemical_registration.repository import (
    MergeEventRepository,
    MoleculeRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetMergeHistoryQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class GetMergeHistory:
    """Query use case: list merge events where molecule is source or target.

    Validates workspace isolation via the molecule.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        merge_event_repo: MergeEventRepository,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo
        self._merge_event_repo = merge_event_repo

    async def __call__(
        self, input: GetMergeHistoryQuery
    ) -> Result[list[MergeEvent], DomainError]:
        async with self._uow:
            mol = await self._molecule_repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            events = await self._merge_event_repo.find_by_molecule(input.workspace_id, input.molecule_id)
            return Success(events)
