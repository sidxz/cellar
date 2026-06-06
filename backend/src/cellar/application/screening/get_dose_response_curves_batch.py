"""GetDoseResponseCurvesBatch — bulk read of dose-response curves by id.

Used by the campaign UI to inline DR plots in the results grid. Curves are
returned with ``raw_data`` already condensed to the ``[{x, y}]`` shape consumed
by the FE sparkline. Identity fields on the curve (molecule name, batch number,
etc.) are not populated here — callers correlate by ``molecule_id`` and fetch
identity through a separate query.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening import _condense_raw_data
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.repository import DoseResponseCurveRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class GetDoseResponseCurvesBatchQuery(Query):
    workspace_id: uuid.UUID
    curve_ids: list[uuid.UUID]


class GetDoseResponseCurvesBatch:
    def __init__(self, uow: UnitOfWork, repo: DoseResponseCurveRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: GetDoseResponseCurvesBatchQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[DoseResponseCurve], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        if not input.curve_ids:
            return Success([])
        async with self._uow:
            curves = await self._repo.find_by_ids(input.workspace_id, input.curve_ids)
        for c in curves:
            if c.raw_data:
                c.raw_data = _condense_raw_data(c.raw_data)
        return Success(curves)
