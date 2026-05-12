"""ListCollectionsForMolecule query — collections containing a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.repository import CollectionRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListCollectionsForMoleculeQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class ListCollectionsForMolecule:
    def __init__(self, uow: UnitOfWork, repo: CollectionRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListCollectionsForMoleculeQuery, auth: AuthContext | None = None
    ) -> Result[list[Collection], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            collections = await self._repo.find_collections_containing(
                input.workspace_id, input.molecule_id
            )
            return Success(collections)
