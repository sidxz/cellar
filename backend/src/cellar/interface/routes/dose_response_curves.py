"""Batch read endpoints for DoseResponseCurves.

The campaign UI uses POST /curves:batch to inline DR plots in the results
grid. The cap of 500 ids per request comfortably fits typical campaigns
(1 channel * <=200 compounds = <=200 curves) while bounding payload size.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cellar.application.screening.get_dose_response_curves_batch import (
    GetDoseResponseCurvesBatchQuery,
)
from cellar.interface.dependencies import AuthDep, GetDoseResponseCurvesBatchDep
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes.readout_data import DoseResponseCurveResponse

router = APIRouter(prefix="/api/v1/dose-response", tags=["dose-response"])


class BatchCurvesRequest(BaseModel):
    curve_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class BatchCurvesResponse(BaseModel):
    curves: list[DoseResponseCurveResponse]


@router.post("/curves:batch", response_model=BatchCurvesResponse)
async def get_curves_batch(
    body: BatchCurvesRequest,
    auth: AuthDep,
    uc: GetDoseResponseCurvesBatchDep,
) -> BatchCurvesResponse:
    """Look up dose-response curves by id, scoped to the caller's workspace.

    Returns an empty list for missing ids or curves in a foreign workspace.
    Cap: 500 ids per request (enforced by Pydantic ``max_length`` on the request body).

    Note: identity fields (``registration_number``, ``molecule_name``,
    ``synonyms``, ``smiles``, ``batch_number``) are intentionally returned
    as ``None`` — callers correlate curves to molecules by ``molecule_id``
    and fetch identity through a separate query (e.g. ``useMoleculesByIds``
    on the campaign frontend). Use the enriched ``GET
    /api/v1/protocols/{protocol_id}/compounds/{molecule_id}/dose-response``
    endpoint if you need identity fields populated.
    """
    query = GetDoseResponseCurvesBatchQuery(
        workspace_id=auth.workspace_id, curve_ids=body.curve_ids
    )
    curves = result_to_response(await uc(query, auth=auth))
    return BatchCurvesResponse(
        curves=[DoseResponseCurveResponse.from_domain(c) for c in curves]
    )
