"""GetRun and ListRunsByProtocol query use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetRunQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListRunsByProtocolQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


class GetRun:
    def __init__(self, uow: UnitOfWork, repo: RunRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetRunQuery, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            return Success(run)


class ListRunsByProtocol:
    def __init__(self, uow: UnitOfWork, repo: RunRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListRunsByProtocolQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[Run], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            runs = await self._repo.find_by_protocol(input.workspace_id, input.protocol_id)
            return Success(runs)
