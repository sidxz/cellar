from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.shared.errors import DomainError, NotFoundError


# Back-compat: kept so existing imports keep working until they migrate to the
# Result path. New callers should pattern-match on ``Result[ScaffoldTreeJob, _]``
# and use ``result_to_response`` for HTTP conversion.
class ScaffoldTreeJobNotFound(Exception):
    pass


@dataclass(frozen=True)
class GetScaffoldTreeJobInput:
    job_id: UUID
    workspace_id: UUID


class GetScaffoldTreeJob:
    def __init__(self, *, repository: ScaffoldTreeJobRepository, uow: UnitOfWork) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(
        self, payload: GetScaffoldTreeJobInput
    ) -> Result[ScaffoldTreeJob, DomainError]:
        async with self._uow:
            job = await self._repo.find_by_id(payload.job_id, workspace_id=payload.workspace_id)
        if job is None:
            return Failure(NotFoundError("ScaffoldTreeJob", str(payload.job_id)))
        return Success(job)
