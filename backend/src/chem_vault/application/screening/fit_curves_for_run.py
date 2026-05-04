"""FitCurvesForRun — load run context and delegate to FitDoseResponseCurves."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext
from chem_vault.application.screening.fit_dose_response import FitDoseResponseCurves
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class FitCurvesForRunQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


class FitCurvesForRun:
    """Load run, protocol, readout data and fit dose-response curves.

    Encapsulates the data-loading step that was previously done inline
    in the route handler, then delegates fitting to FitDoseResponseCurves.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_data_repo: ReadoutDataRepository,
        fit_dose_response: FitDoseResponseCurves,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._rd_repo = readout_data_repo
        self._fit = fit_dose_response

    async def __call__(
        self,
        input: FitCurvesForRunQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[DoseResponseCurve], DomainError]:
        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(
                input.workspace_id, input.run_id
            )
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, run.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(run.protocol_id)))

            readout_data = await self._rd_repo.find_by_run(
                input.workspace_id, input.run_id
            )

        # Fit curves (uses its own UoW internally)
        return await self._fit.fit_for_run(
            run=run, protocol=protocol, readout_data=readout_data
        )
