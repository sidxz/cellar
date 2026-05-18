from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob


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

    async def execute(self, payload: GetScaffoldTreeJobInput) -> ScaffoldTreeJob:
        async with self._uow:
            job = await self._repo.find_by_id(payload.job_id, workspace_id=payload.workspace_id)
        if job is None:
            raise ScaffoldTreeJobNotFound(str(payload.job_id))
        return job
