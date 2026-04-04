"""ListDoseResponseByRun query use case."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.repository import DoseResponseCurveRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class ListDoseResponseByRun:
    def __init__(self, uow: UnitOfWork, repo: DoseResponseCurveRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        run_id: uuid.UUID,
        auth: AuthContext | None = None,
    ) -> Result[list[DoseResponseCurve], DomainError]:
        if auth is None:
            return Failure(NotFoundError("DoseResponseCurve"))
        async with self._uow:
            curves = await self._repo.find_by_run(auth.workspace_id, run_id)
            return Success(curves)
