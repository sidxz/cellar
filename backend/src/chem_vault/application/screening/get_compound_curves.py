"""GetCompoundCurves — all DR curves for a compound in a protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext
from chem_vault.application.screening.compound_curves_reader import (
    CompoundCurvesReader,
)
from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class GetCompoundCurvesQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    molecule_id: uuid.UUID


class GetCompoundCurves:
    def __init__(self, reader: CompoundCurvesReader) -> None:
        self._reader = reader

    async def __call__(
        self, input: GetCompoundCurvesQuery, auth: AuthContext | None = None
    ) -> Result[list[dict], DomainError]:
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
                    "fitted_unit": r.fitted_unit,
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
