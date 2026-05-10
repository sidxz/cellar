"""GetSample and ListSamples query use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import SampleRepository
from chem_vault.domain.inventory.sample import Sample
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetSampleQuery(Query):
    workspace_id: uuid.UUID
    sample_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListSamplesByBatchQuery(Query):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID


class GetSample:
    def __init__(self, uow: UnitOfWork, repo: SampleRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetSampleQuery, auth: AuthContext | None = None
    ) -> Result[Sample, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            sample = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.sample_id
            )
            if sample is None:
                return Failure(NotFoundError("Sample", str(input.sample_id)))
            return Success(sample)


class ListSamplesByBatch:
    def __init__(self, uow: UnitOfWork, repo: SampleRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListSamplesByBatchQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[Sample], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            samples = await self._repo.find_by_batch(
                input.workspace_id, input.batch_id
            )
            return Success(samples)
