"""GetCompoundCurves — all DR curves for a compound in a protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.screening.compound_curves_reader import (
    CompoundCurvesReader,
)
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class GetCompoundCurvesQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    molecule_id: uuid.UUID


class GetCompoundCurves:
    def __init__(
        self,
        reader: CompoundCurvesReader,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
    ) -> None:
        self._reader = reader
        self._uow = uow
        self._protocol_repo = protocol_repo

    async def __call__(
        self, input: GetCompoundCurvesQuery, auth: AuthContext | None = None
    ) -> Result[list[dict], DomainError]:
        require_workspace_role(auth, "viewer")
        # IC50 unit comes from the protocol — single source of truth.
        async with self._uow:
            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
        dose_unit = protocol.dose_unit.value if protocol else "uM"

        rows = await self._reader.get_curves(
            workspace_id=input.workspace_id,
            protocol_id=input.protocol_id,
            molecule_id=input.molecule_id,
        )
        items = []
        for r in rows:
            items.append(
                {
                    "id": str(r.id),
                    "workspace_id": str(r.workspace_id),
                    "molecule_id": str(r.molecule_id),
                    "molecule_name": None,
                    "batch_id": str(r.batch_id),
                    "batch_number": None,
                    "protocol_id": str(r.protocol_id),
                    "run_id": str(r.run_id),
                    "curve_type": r.curve_type,
                    "fitted_value": r.fitted_value,
                    "fitted_unit": dose_unit,
                    "hill_slope": r.hill_slope,
                    "top": r.top,
                    "bottom": r.bottom,
                    "r_squared": r.r_squared,
                    "confidence_interval_low": r.confidence_interval_low,
                    "confidence_interval_high": r.confidence_interval_high,
                    "num_points": r.num_points,
                    "curve_class": r.curve_class,
                    "raw_data": r.raw_data,
                    "excluded_points": r.excluded_points,
                }
            )
        return Success(items)
