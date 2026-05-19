"""GetUmapClusterJob — fetch a single UMAP cluster job by ID, scoped to workspace."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.umap_job import UmapJob
from cellar.domain.shared.errors import DomainError, NotFoundError


# Back-compat: kept so existing imports keep working until they migrate to the
# Result path. New callers should pattern-match on ``Result[UmapJob, _]`` and
# use ``result_to_response`` for HTTP conversion.
class UmapJobNotFound(Exception):
    """Raised when a UMAP cluster job is not visible in the caller's workspace."""


@dataclass(frozen=True)
class GetUmapClusterJobInput:
    job_id: UUID
    workspace_id: UUID


class GetUmapClusterJob:
    def __init__(self, *, repository: UmapJobRepository, uow: UnitOfWork) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(
        self, payload: GetUmapClusterJobInput
    ) -> Result[UmapJob, DomainError]:
        async with self._uow:
            job = await self._repo.find_by_id(
                payload.job_id, workspace_id=payload.workspace_id
            )
        if job is None:
            return Failure(NotFoundError("UmapJob", str(payload.job_id)))
        return Success(job)
