"""CancelUmapClusterJob — cancel a pending or running UMAP cluster job."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.sar_analysis.start_umap_cluster_job import UmapClusterOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.umap_job import InvalidUmapJobTransition


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

    async def execute(self, job_id: UUID) -> None:
        async with self._uow:
            job = await self._repo.find_by_id(job_id)
            if job is None:
                return
            try:
                cancelled = job.mark_cancelled(datetime.now(timezone.utc))
                await self._repo.save(cancelled)
                await self._uow.commit()
            except InvalidUmapJobTransition:
                return
        await self._orchestrator.cancel(job_id=job_id)
