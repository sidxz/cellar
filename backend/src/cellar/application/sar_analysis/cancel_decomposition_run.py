from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.sar_analysis.start_decomposition_run import RGroupDecompositionOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.shared.async_job import InvalidJobTransition
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class CancelDecompositionRunInput:
    run_id: UUID
    workspace_id: UUID
    now: datetime


class CancelDecompositionRun:
    def __init__(
        self,
        *,
        repository: RGroupDecompositionRunRepository,
        orchestrator: RGroupDecompositionOrchestrator,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow

    async def execute(
        self, payload: CancelDecompositionRunInput
    ) -> Result[RGroupDecompositionRun, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(payload.workspace_id, payload.run_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            try:
                run.mark_cancelled(payload.now)
            except InvalidJobTransition:
                return Success(run)  # already terminal — idempotent no-op
            await self._repo.save(run)
            await self._uow.commit()
        await self._orchestrator.cancel(run_id=run.id)
        return Success(run)
