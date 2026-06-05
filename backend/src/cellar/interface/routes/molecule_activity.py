"""Molecule Activity Detail API route.

Provides all dose-response curves for a molecule grouped by protocol,
powering the compound detail side panel in the search UI.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.screening.get_molecule_activity_detail import (
    GetMoleculeActivityDetailQuery,
    MoleculeActivityDetail,
)
from cellar.interface.dependencies import AuthDep, GetMoleculeActivityDetailDep
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._intercept_response import (
    InterceptSpecResponse,
    InterceptValueResponse,
)

__all__ = ["InterceptSpecResponse", "InterceptValueResponse"]

router = APIRouter(prefix="/api/v1/molecules", tags=["molecule-activity"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CurveDetailResponse(BaseModel):
    curve_id: uuid.UUID
    run_id: uuid.UUID
    # Owning Run's date — surfaced so the drawer's selection logic can
    # honor the toolbar's "latest run" rule without a second BE call.
    # Nullable in case the owning Run was deleted out-of-band.
    run_date: date | None = None
    batch_id: uuid.UUID
    readout_definition_id: uuid.UUID
    curve_type: str
    fitted_value: float
    fitted_unit: str
    hill_slope: float
    r_squared: float
    curve_class: str | None = None
    top: float
    bottom: float
    num_points: int
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    raw_data: list[dict[str, Any]] = []
    # Mirrors the run-page DRC response: surfaces fit-quality warnings and
    # secondary intercepts (IC90/EC10/etc.) so the search-detail panel renders
    # the same chemistry-quality signals as the protocol-runs view.
    excluded_points: list[dict[str, Any]] | None = None
    fit_quality_warnings: list[str] = []
    intercept_values: list[InterceptValueResponse] = []


class ProtocolCurveGroupResponse(BaseModel):
    protocol_id: uuid.UUID
    protocol_name: str
    protocol_type: str
    target_id: uuid.UUID | None = None
    curves: list[CurveDetailResponse] = []


class MoleculeActivityDetailResponse(BaseModel):
    molecule_id: uuid.UUID
    protocols: list[ProtocolCurveGroupResponse] = []

    @classmethod
    def from_dto(cls, dto: MoleculeActivityDetail) -> MoleculeActivityDetailResponse:
        return cls(
            molecule_id=dto.molecule_id,
            protocols=[
                ProtocolCurveGroupResponse(
                    protocol_id=g.protocol_id,
                    protocol_name=g.protocol_name,
                    protocol_type=g.protocol_type,
                    target_id=g.target_id,
                    curves=[
                        CurveDetailResponse(
                            curve_id=c.curve_id,
                            run_id=c.run_id,
                            run_date=c.run_date,
                            batch_id=c.batch_id,
                            readout_definition_id=c.readout_definition_id,
                            curve_type=c.curve_type,
                            fitted_value=c.fitted_value,
                            fitted_unit=c.fitted_unit,
                            hill_slope=c.hill_slope,
                            r_squared=c.r_squared,
                            curve_class=c.curve_class,
                            top=c.top,
                            bottom=c.bottom,
                            num_points=c.num_points,
                            confidence_interval_low=c.confidence_interval_low,
                            confidence_interval_high=c.confidence_interval_high,
                            raw_data=c.raw_data,
                            excluded_points=c.excluded_points,
                            fit_quality_warnings=c.fit_quality_warnings,
                            intercept_values=[
                                InterceptValueResponse.from_domain(iv) for iv in c.intercept_values
                            ],
                        )
                        for c in g.curves
                    ],
                )
                for g in dto.protocols
            ],
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{molecule_id}/activity-detail",
    response_model=MoleculeActivityDetailResponse,
)
async def get_molecule_activity_detail(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    uc: GetMoleculeActivityDetailDep,
) -> MoleculeActivityDetailResponse:
    """Get all dose-response curves for a molecule, grouped by protocol."""
    query = GetMoleculeActivityDetailQuery(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
    )
    result = await uc(query, auth=auth)
    dto = result_to_response(result)
    return MoleculeActivityDetailResponse.from_dto(dto)
