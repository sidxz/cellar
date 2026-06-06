"""GetCollection / ListCollections queries — retrieve collection(s)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.pagination import PageResult, encode_ts_cursor
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.repository import CollectionRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            collection = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.collection_id
            )
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
    # Keyset cursor: (updated_at, id) of the last row of the prior page.
    cursor: tuple[datetime, uuid.UUID] | None = None
    limit: int | None = None
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"


class ListCollections:
    def __init__(self, uow: UnitOfWork, repo: CollectionRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListCollectionsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Collection], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            collections = await self._repo.find_by_workspace(
                input.workspace_id,
                project_ids=list(input.project_ids) if input.project_ids else None,
                cursor=input.cursor,
                limit=fetch_limit,
                tags=input.tags,
                tag_logic=input.tag_logic,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(collections) > effective_limit:
                collections = collections[:effective_limit]
                last = collections[-1]
                next_cursor = encode_ts_cursor(last.updated_at, last.id)

            return Success(PageResult(items=collections, next_cursor=next_cursor))
