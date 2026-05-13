"""ListReadoutDataByRun query use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import ReadoutDataRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListReadoutDataByRunQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


class ListReadoutDataByRun:
    def __init__(self, uow: UnitOfWork, repo: ReadoutDataRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListReadoutDataByRunQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[ReadoutData], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            data = await self._repo.find_by_run(input.workspace_id, input.run_id)
            return Success(data)
