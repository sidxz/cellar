"""GetSavedSearch / ListSavedSearches queries — retrieve saved search(es)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.repository import SavedSearchRepository
from cellar.domain.research_organization.saved_search import SavedSearch
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetSavedSearchQuery(Query):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID


class GetSavedSearch:
    def __init__(self, uow: UnitOfWork, repo: SavedSearchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetSavedSearchQuery, auth: AuthContext | None = None
    ) -> Result[SavedSearch, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            search = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.saved_search_id
            )
            if search is None:
                return Failure(NotFoundError("SavedSearch", str(input.saved_search_id)))
            return Success(search)


@dataclass(frozen=True, kw_only=True)
class ListSavedSearchesQuery(Query):
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None


class ListSavedSearches:
    def __init__(self, uow: UnitOfWork, repo: SavedSearchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListSavedSearchesQuery, auth: AuthContext | None = None
    ) -> Result[list[SavedSearch], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            if input.created_by is not None:
                searches = await self._repo.find_by_creator(input.workspace_id, input.created_by)
            elif input.project_id is not None:
                searches = await self._repo.find_by_project(input.workspace_id, input.project_id)
            else:
                searches = await self._repo.find_by_workspace(input.workspace_id)
            return Success(searches)
