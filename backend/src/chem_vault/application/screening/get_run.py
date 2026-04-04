"""GetRun and ListRunsByProtocol query use cases."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import RunRepository
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class GetRun:
    def __init__(self, uow: UnitOfWork, repo: RunRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, run_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(run_id)
            if run is None:
                return Failure(NotFoundError("Run"))
            require_same_workspace(auth, run.workspace_id)
            return Success(run)


class ListRunsByProtocol:
    def __init__(self, uow: UnitOfWork, repo: RunRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        protocol_id: uuid.UUID,
        auth: AuthContext | None = None,
    ) -> Result[list[Run], DomainError]:
        if auth is None:
            return Failure(NotFoundError("Run"))
        async with self._uow:
            runs = await self._repo.find_by_protocol(
                auth.workspace_id, protocol_id
            )
            return Success(runs)
