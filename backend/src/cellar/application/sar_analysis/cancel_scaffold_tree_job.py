from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.sar_analysis.start_scaffold_tree_job import ScaffoldTreeOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.shared.async_job import InvalidJobTransition
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class CancelScaffoldTreeJobInput:
    job_id: UUID
    workspace_id: UUID
    now: datetime


class CancelScaffoldTreeJob:
    def __init__(
        self,
        *,
        repository: ScaffoldTreeJobRepository,
        orchestrator: ScaffoldTreeOrchestrator,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow

    async def execute(
        self, payload: CancelScaffoldTreeJobInput
    ) -> Result[ScaffoldTreeJob, DomainError]:
        async with self._uow:
            job = await self._repo.find_by_id_in_workspace(payload.workspace_id, payload.job_id)
            if job is None:
                return Failure(NotFoundError("ScaffoldTreeJob", str(payload.job_id)))
            try:
                job.mark_cancelled(payload.now)
            except InvalidJobTransition:
                return Success(job)  # already terminal — idempotent no-op
            await self._repo.save(job)
            await self._uow.commit()
        await self._orchestrator.cancel(job_id=job.id)
        return Success(job)
