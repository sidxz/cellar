"""Readout data and dose-response curve API routes."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
    BulkCreateReadoutDataCommand,
    ReadoutDataItem,
)
from chem_vault.application.screening.create_dose_response import (
    CreateDoseResponseCurve,
    CreateDoseResponseCurveCommand,
)
from chem_vault.application.screening.create_readout_data import (
    CreateReadoutData,
    CreateReadoutDataCommand,
)
from chem_vault.application.screening.get_dose_response import ListDoseResponseByRun
from chem_vault.application.screening.get_readout_data import ListReadoutDataByRun
from chem_vault.interface.dependencies import AuthDep, get_container
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["readout-data"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ReadoutDataResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    well_id: uuid.UUID | None = None
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    readout_definition_id: uuid.UUID
    value_numeric: float | None = None
    value_qualifier: str | None = None
    value_text: str | None = None
    is_outlier: bool

    @classmethod
    def from_domain(cls, rd) -> ReadoutDataResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=rd.id,
            workspace_id=rd.workspace_id,
            run_id=rd.run_id,
            well_id=rd.well_id,
            molecule_id=rd.molecule_id,
            batch_id=rd.batch_id,
            readout_definition_id=rd.readout_definition_id,
            value_numeric=rd.value.value if rd.value else None,
            value_qualifier=rd.value.qualifier.value if rd.value else None,
            value_text=rd.value_text,
            is_outlier=rd.is_outlier,
        )


class DoseResponseCurveResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    protocol_id: uuid.UUID
    run_id: uuid.UUID
    curve_type: str
    fitted_value: float
    fitted_unit: str
    hill_slope: float
    top: float
    bottom: float
    r_squared: float
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    num_points: int
    curve_class: str | None = None
    raw_data: list[dict[str, Any]] | None = None
    excluded_points: list[dict[str, Any]] | None = None

    @classmethod
    def from_domain(cls, c) -> DoseResponseCurveResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=c.id,
            workspace_id=c.workspace_id,
            molecule_id=c.molecule_id,
            batch_id=c.batch_id,
            protocol_id=c.protocol_id,
            run_id=c.run_id,
            curve_type=c.curve_type.value,
            fitted_value=c.fitted_value,
            fitted_unit=c.fitted_unit,
            hill_slope=c.hill_slope,
            top=c.top,
            bottom=c.bottom,
            r_squared=c.r_squared,
            confidence_interval_low=c.confidence_interval_low,
            confidence_interval_high=c.confidence_interval_high,
            num_points=c.num_points,
            curve_class=c.curve_class.value if c.curve_class else None,
            raw_data=c.raw_data or None,
            excluded_points=c.excluded_points,
        )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateReadoutDataRequest(BaseModel):
    run_id: uuid.UUID
    well_id: uuid.UUID | None = None
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    readout_definition_id: uuid.UUID
    value_numeric: float | None = None
    value_qualifier: str | None = None
    value_text: str | None = None
    is_outlier: bool = False


class BulkReadoutDataItem(BaseModel):
    """Request item for bulk readout import.

    Supports both UUID-based references (molecule_id, batch_id,
    readout_definition_id) and human-readable alternatives
    (registration_number, batch_number, readout_definition_name).
    When both are provided, the UUID takes precedence.
    """
    run_id: uuid.UUID
    well_id: uuid.UUID | None = None
    molecule_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    readout_definition_id: uuid.UUID | None = None
    # Human-readable alternatives
    registration_number: str | None = None
    batch_number: str | None = None
    readout_definition_name: str | None = None
    value_numeric: float | None = None
    value_qualifier: str | None = None
    value_text: str | None = None
    is_outlier: bool = False


class BulkReadoutDataRequest(BaseModel):
    items: list[BulkReadoutDataItem]


class BulkReadoutDataResponse(BaseModel):
    total_count: int
    success_count: int
    error_count: int
    errors: list[dict] = []


class CreateDoseResponseCurveRequest(BaseModel):
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    protocol_id: uuid.UUID
    run_id: uuid.UUID
    curve_type: str
    fitted_value: float
    fitted_unit: str
    hill_slope: float
    top: float
    bottom: float
    r_squared: float
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    num_points: int
    curve_class: str | None = None
    raw_data: list[dict[str, Any]] | None = None
    excluded_points: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Dependency resolvers
# ---------------------------------------------------------------------------


def _create_readout(c: Annotated[Container, Depends(get_container)]) -> CreateReadoutData:
    return c[CreateReadoutData]

def _bulk_create_readout(c: Annotated[Container, Depends(get_container)]) -> BulkCreateReadoutData:
    return c[BulkCreateReadoutData]

def _list_readout(c: Annotated[Container, Depends(get_container)]) -> ListReadoutDataByRun:
    return c[ListReadoutDataByRun]

def _create_dose_response(c: Annotated[Container, Depends(get_container)]) -> CreateDoseResponseCurve:
    return c[CreateDoseResponseCurve]

def _list_dose_response(c: Annotated[Container, Depends(get_container)]) -> ListDoseResponseByRun:
    return c[ListDoseResponseByRun]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/readout-data", response_model=ReadoutDataResponse, status_code=201)
async def create_readout_data(
    auth: AuthDep,
    body: CreateReadoutDataRequest,
    uc: Annotated[CreateReadoutData, Depends(_create_readout)],
) -> ReadoutDataResponse:
    cmd = CreateReadoutDataCommand(
        workspace_id=auth.workspace_id,
        run_id=body.run_id,
        well_id=body.well_id,
        molecule_id=body.molecule_id,
        batch_id=body.batch_id,
        readout_definition_id=body.readout_definition_id,
        value_numeric=body.value_numeric,
        value_qualifier=body.value_qualifier,
        value_text=body.value_text,
        is_outlier=body.is_outlier,
    )
    result = await uc(cmd, auth=auth)
    return ReadoutDataResponse.from_domain(result_to_response(result))


@router.post("/readout-data/bulk", response_model=BulkReadoutDataResponse, status_code=201)
async def bulk_create_readout_data(
    auth: AuthDep,
    body: BulkReadoutDataRequest,
    uc: Annotated[BulkCreateReadoutData, Depends(_bulk_create_readout)],
) -> BulkReadoutDataResponse:
    cmd = BulkCreateReadoutDataCommand(
        workspace_id=auth.workspace_id,
        items=[
            ReadoutDataItem(
                run_id=item.run_id,
                well_id=item.well_id,
                molecule_id=item.molecule_id,
                batch_id=item.batch_id,
                readout_definition_id=item.readout_definition_id,
                registration_number=item.registration_number,
                batch_number=item.batch_number,
                readout_definition_name=item.readout_definition_name,
                value_numeric=item.value_numeric,
                value_qualifier=item.value_qualifier,
                value_text=item.value_text,
                is_outlier=item.is_outlier,
            )
            for item in body.items
        ],
    )
    result = await uc(cmd, auth=auth)
    data = result_to_response(result)
    return BulkReadoutDataResponse(
        total_count=data.total_count,
        success_count=data.success_count,
        error_count=data.error_count,
        errors=data.errors,
    )


@router.get("/readout-data", response_model=list[ReadoutDataResponse])
async def list_readout_data(
    auth: AuthDep,
    run_id: Annotated[uuid.UUID, Query()],
    uc: Annotated[ListReadoutDataByRun, Depends(_list_readout)],
) -> list[ReadoutDataResponse]:
    result = await uc(run_id, auth=auth)
    data = result_to_response(result)
    return [ReadoutDataResponse.from_domain(rd) for rd in data]


@router.post("/dose-response-curves", response_model=DoseResponseCurveResponse, status_code=201)
async def create_dose_response_curve(
    auth: AuthDep,
    body: CreateDoseResponseCurveRequest,
    uc: Annotated[CreateDoseResponseCurve, Depends(_create_dose_response)],
) -> DoseResponseCurveResponse:
    cmd = CreateDoseResponseCurveCommand(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        batch_id=body.batch_id,
        protocol_id=body.protocol_id,
        run_id=body.run_id,
        curve_type=body.curve_type,
        fitted_value=body.fitted_value,
        fitted_unit=body.fitted_unit,
        hill_slope=body.hill_slope,
        top=body.top,
        bottom=body.bottom,
        r_squared=body.r_squared,
        confidence_interval_low=body.confidence_interval_low,
        confidence_interval_high=body.confidence_interval_high,
        num_points=body.num_points,
        curve_class=body.curve_class,
        raw_data=body.raw_data or [],
        excluded_points=body.excluded_points,
    )
    result = await uc(cmd, auth=auth)
    return DoseResponseCurveResponse.from_domain(result_to_response(result))


@router.get("/dose-response-curves", response_model=list[DoseResponseCurveResponse])
async def list_dose_response_curves(
    auth: AuthDep,
    run_id: Annotated[uuid.UUID, Query()],
    uc: Annotated[ListDoseResponseByRun, Depends(_list_dose_response)],
) -> list[DoseResponseCurveResponse]:
    result = await uc(run_id, auth=auth)
    curves = result_to_response(result)
    return [DoseResponseCurveResponse.from_domain(c) for c in curves]
