"""GetCollection / ListCollections queries — retrieve collection(s)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.collection import Collection
from chem_vault.domain.research_organization.repository import CollectionRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetCollectionQuery(Query):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID


class GetCollection:
    def __init__(self, uow: UnitOfWork, repo: CollectionRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetCollectionQuery, auth: AuthContext | None = None
    ) -> Result[Collection, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            collection = await self._repo.find_by_id_in_workspace(input.workspace_id, input.collection_id)
            if collection is None:
                return Failure(NotFoundError("Collection", str(input.collection_id)))
            return Success(collection)


@dataclass(frozen=True, kw_only=True)
class ListCollectionsQuery(Query):
    workspace_id: uuid.UUID
    # Empty/None means workspace-wide; non-empty restricts to the union of
    # collections that belong to any of these projects (multi-project scoping
    # for the search picker).
    project_ids: tuple[uuid.UUID, ...] | None = None


class ListCollections:
    def __init__(self, uow: UnitOfWork, repo: CollectionRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListCollectionsQuery, auth: AuthContext | None = None
    ) -> Result[list[Collection], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            collections = await self._repo.find_by_workspace(
                input.workspace_id,
                project_ids=list(input.project_ids) if input.project_ids else None,
            )
            return Success(collections)
