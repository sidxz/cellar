"""GetUmapClusterJob — fetch a single UMAP cluster job by ID."""

from __future__ import annotations

from uuid import UUID

from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.domain.sar_analysis.umap_job import UmapJob


class GetUmapClusterJob:
    def __init__(self, repository: UmapJobRepository) -> None:
        self._repo = repository

    async def execute(self, job_id: UUID) -> UmapJob | None:
        return await self._repo.find_by_id(job_id)
