"""GetBatch and ListBatches query use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetBatchQuery(Query):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListBatchesByMoleculeQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class GetBatch:
    def __init__(self, uow: UnitOfWork, repo: BatchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetBatchQuery, auth: AuthContext | None = None
    ) -> Result[Batch, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            batch = await self._repo.find_by_id_in_workspace(input.workspace_id, input.batch_id)
            if batch is None:
                return Failure(NotFoundError("Batch", str(input.batch_id)))
            return Success(batch)


class ListBatchesByMolecule:
    def __init__(self, uow: UnitOfWork, repo: BatchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListBatchesByMoleculeQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[Batch], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            batches = await self._repo.find_by_molecule(input.workspace_id, input.molecule_id)
            return Success(batches)
