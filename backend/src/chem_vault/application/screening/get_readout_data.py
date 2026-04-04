"""ListReadoutDataByRun query use case."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import ReadoutDataRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class ListReadoutDataByRun:
    def __init__(self, uow: UnitOfWork, repo: ReadoutDataRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        run_id: uuid.UUID,
        auth: AuthContext | None = None,
    ) -> Result[list[ReadoutData], DomainError]:
        if auth is None:
            return Failure(NotFoundError("ReadoutData"))
        async with self._uow:
            data = await self._repo.find_by_run(auth.workspace_id, run_id)
            return Success(data)
