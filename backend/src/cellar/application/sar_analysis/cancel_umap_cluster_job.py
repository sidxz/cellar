"""CancelUmapClusterJob — cancel a pending or running UMAP cluster job."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.sar_analysis.start_umap_cluster_job import UmapClusterOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.umap_job import InvalidUmapJobTransition, UmapJob
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class CancelUmapClusterJobInput:
    job_id: UUID
    workspace_id: UUID


class CancelUmapClusterJob:
    def __init__(
        self,
        *,
        repository: UmapJobRepository,
        uow: UnitOfWork,
        orchestrator: UmapClusterOrchestrator,
    ) -> None:
        self._repo = repository
        self._uow = uow
        self._orchestrator = orchestrator

    async def execute(self, payload: CancelUmapClusterJobInput) -> Result[UmapJob, DomainError]:
        async with self._uow:
            job = await self._repo.find_by_id(payload.job_id, workspace_id=payload.workspace_id)
            if job is None:
                return Failure(NotFoundError("UmapJob", str(payload.job_id)))
            try:
                cancelled = job.mark_cancelled(datetime.now(UTC))
            except InvalidUmapJobTransition:
                return Success(job)  # already terminal — idempotent no-op
            await self._repo.save(cancelled)
            await self._uow.commit()
        await self._orchestrator.cancel(job_id=payload.job_id)
        return Success(cancelled)
