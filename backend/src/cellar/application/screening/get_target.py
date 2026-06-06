"""GetTarget and ListTargets query use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetTargetQuery(Query):
    workspace_id: uuid.UUID
    target_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListTargetsQuery(Query):
    workspace_id: uuid.UUID
    cursor_id: uuid.UUID | None = None
    limit: int | None = None


class GetTarget:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetTargetQuery, auth: AuthContext | None = None
    ) -> Result[Target, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            target = await self._repo.find_by_id_in_workspace(input.workspace_id, input.target_id)
            if target is None:
                return Failure(NotFoundError("Target", str(input.target_id)))
            return Success(target)


class ListTargets:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListTargetsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Target], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            targets = await self._repo.find_by_workspace(
                input.workspace_id,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(targets) > effective_limit:
                targets = targets[:effective_limit]
                next_cursor = str(targets[-1].id)

            return Success(PageResult(items=targets, next_cursor=next_cursor))
