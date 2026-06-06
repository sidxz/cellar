"""ListMoleculesByIds — bulk lookup by id, workspace-scoped.

Used by the campaign UI to enrich result rows with identity fields (name,
registration number, SMILES) given a set of molecule ids returned from another
query (e.g. the dose-response batch endpoint).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListMoleculesByIdsQuery(Query):
    workspace_id: uuid.UUID
    ids: list[uuid.UUID]


class ListMoleculesByIds:
    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListMoleculesByIdsQuery, auth: AuthContext | None = None
    ) -> Result[list[Molecule], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        if not input.ids:
            return Success([])
        async with self._uow:
            molecules = await self._repo.find_by_ids(input.workspace_id, input.ids)
        return Success(molecules)
