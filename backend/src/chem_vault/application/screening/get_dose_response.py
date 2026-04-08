"""ListDoseResponseByRun query use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.repository import DoseResponseCurveRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListDoseResponseByRunQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


class ListDoseResponseByRun:
    def __init__(self, uow: UnitOfWork, repo: DoseResponseCurveRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListDoseResponseByRunQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[DoseResponseCurve], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            curves = await self._repo.find_by_run(input.workspace_id, input.run_id)
            return Success(curves)
