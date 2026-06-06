"""GetMergeHistory query — retrieve merge events for a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.merge_event import MergeEvent
from cellar.domain.chemical_registration.repository import (
    MergeEventRepository,
    MoleculeRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


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
        self, input: GetMergeHistoryQuery, auth: AuthContext | None = None
    ) -> Result[list[MergeEvent], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            mol = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.molecule_id
            )
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            events = await self._merge_event_repo.find_by_molecule(
                input.workspace_id, input.molecule_id
            )
            return Success(events)
