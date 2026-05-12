"""Batch read endpoints for DoseResponseCurves.

The campaign UI uses POST /curves:batch to inline DR plots in the results
grid. The cap of 500 ids per request comfortably fits typical campaigns
(1 channel * <=200 compounds = <=200 curves) while bounding payload size.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from chem_vault.interface.dependencies import AuthDep, UoWDep
from chem_vault.interface.routes.readout_data import DoseResponseCurveResponse

router = APIRouter(prefix="/api/v1/dose-response", tags=["dose-response"])


class BatchCurvesRequest(BaseModel):
    curve_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class BatchCurvesResponse(BaseModel):
    curves: list[DoseResponseCurveResponse]


@router.post("/curves:batch", response_model=BatchCurvesResponse)
async def get_curves_batch(
    body: BatchCurvesRequest,
    auth: AuthDep,
    uow: UoWDep,
) -> BatchCurvesResponse:
    """Look up dose-response curves by id, scoped to the caller's workspace.

    Returns an empty list for missing ids or curves in a foreign workspace.
    Cap: 500 ids per request.
    """
    if len(body.curve_ids) > 500:
        raise HTTPException(status_code=400, detail="max 500 curve ids per request")
    repo = SQLAlchemyDoseResponseCurveRepository(uow)
    async with uow:
        curves = await repo.find_by_ids(auth.workspace_id, body.curve_ids)
    return BatchCurvesResponse(
        curves=[DoseResponseCurveResponse.from_domain(c) for c in curves]
    )
