from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class GetDecompositionRunInput:
    run_id: UUID
    workspace_id: UUID


class GetDecompositionRun:
    def __init__(self, *, repository: RGroupDecompositionRunRepository, uow: UnitOfWork) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(
        self, payload: GetDecompositionRunInput
    ) -> Result[RGroupDecompositionRun, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
        if run is None:
            return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
        return Success(run)
