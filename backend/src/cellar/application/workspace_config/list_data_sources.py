"""ListDataSources query — list all data sources for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.data_source import DataSource
from cellar.domain.workspace_config.repository import DataSourceRepository


@dataclass(frozen=True, kw_only=True)
class ListDataSourcesQuery(Query):
    workspace_id: uuid.UUID
    cursor_id: uuid.UUID | None = None
    limit: int | None = None


class ListDataSources:
    def __init__(self, uow: UnitOfWork, repo: DataSourceRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListDataSourcesQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[DataSource], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            results = await self._repo.find_by_workspace(
                input.workspace_id,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(results) > effective_limit:
                results = results[:effective_limit]
                next_cursor = str(results[-1].id)

            return Success(PageResult(items=results, next_cursor=next_cursor))
