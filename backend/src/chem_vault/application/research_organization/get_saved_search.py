"""GetSavedSearch / ListSavedSearches queries — retrieve saved search(es)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.repository import SavedSearchRepository
from chem_vault.domain.research_organization.saved_search import SavedSearch
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetSavedSearchQuery(Query):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID


class GetSavedSearch:
    def __init__(self, uow: UnitOfWork, repo: SavedSearchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetSavedSearchQuery
    ) -> Result[SavedSearch, DomainError]:
        async with self._uow:
            search = await self._repo.find_by_id_in_workspace(input.workspace_id, input.saved_search_id)
            if search is None:
                return Failure(
                    NotFoundError("SavedSearch", str(input.saved_search_id))
                )
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
        self, input: ListSavedSearchesQuery
    ) -> Result[list[SavedSearch], DomainError]:
        async with self._uow:
            if input.created_by is not None:
                searches = await self._repo.find_by_creator(
                    input.workspace_id, input.created_by
                )
            elif input.project_id is not None:
                searches = await self._repo.find_by_project(input.workspace_id, input.project_id)
            else:
                searches = await self._repo.find_by_workspace(input.workspace_id)
            return Success(searches)
