"""GetUmapClusterJob — fetch a single UMAP cluster job by ID."""

from __future__ import annotations

from uuid import UUID

from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.umap_job import UmapJob


class GetUmapClusterJob:
    def __init__(self, *, repository: UmapJobRepository, uow: UnitOfWork) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(self, job_id: UUID) -> UmapJob | None:
        async with self._uow:
            return await self._repo.find_by_id(job_id)
