"""GetSample and ListSamples query use cases."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import SampleRepository
from chem_vault.domain.inventory.sample import Sample
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class GetSample:
    def __init__(self, uow: UnitOfWork, repo: SampleRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, sample_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Sample, DomainError]:
        async with self._uow:
            sample = await self._repo.find_by_id(sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample"))
            require_same_workspace(auth, sample.workspace_id)
            return Success(sample)


class ListSamplesByBatch:
    def __init__(self, uow: UnitOfWork, repo: SampleRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        batch_id: uuid.UUID,
        auth: AuthContext | None = None,
    ) -> Result[list[Sample], DomainError]:
        if auth is None:
            return Failure(NotFoundError("Sample"))
        async with self._uow:
            samples = await self._repo.find_by_batch(
                auth.workspace_id, batch_id
            )
            return Success(samples)
