from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cellar.application.sar_analysis.get_scaffold_tree_job import ScaffoldTreeJobNotFound
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.sar_analysis.start_scaffold_tree_job import ScaffoldTreeOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.scaffold_tree_job import (
    InvalidScaffoldTreeJobTransition,
    ScaffoldTreeJob,
)


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

    async def execute(self, payload: CancelScaffoldTreeJobInput) -> ScaffoldTreeJob:
        async with self._uow:
            job = await self._repo.find_by_id(payload.job_id, workspace_id=payload.workspace_id)
            if job is None:
                raise ScaffoldTreeJobNotFound(str(payload.job_id))
            try:
                cancelled = job.mark_cancelled(payload.now)
            except InvalidScaffoldTreeJobTransition:
                return job  # already terminal — idempotent no-op
            await self._repo.save(cancelled)
            await self._uow.commit()
        await self._orchestrator.cancel(job_id=job.id)
        return cancelled
