"""GetBatch and ListBatches query use cases."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.batch import Batch
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class GetBatch:
    def __init__(self, uow: UnitOfWork, repo: BatchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, batch_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Batch, DomainError]:
        async with self._uow:
            batch = await self._repo.find_by_id(batch_id)
            if batch is None:
                return Failure(NotFoundError("Batch"))
            require_same_workspace(auth, batch.workspace_id)
            return Success(batch)


class ListBatchesByMolecule:
    def __init__(self, uow: UnitOfWork, repo: BatchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        molecule_id: uuid.UUID,
        auth: AuthContext | None = None,
    ) -> Result[list[Batch], DomainError]:
        if auth is None:
            return Failure(NotFoundError("Batch"))
        async with self._uow:
            batches = await self._repo.find_by_molecule(
                auth.workspace_id, molecule_id
            )
            return Success(batches)
