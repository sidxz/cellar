"""Readout data and dose-response curve API routes."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from cellar.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
    BulkCreateReadoutDataCommand,
    ReadoutDataItem,
)
from cellar.application.screening.create_dose_response import (
    CreateDoseResponseCurve,
    CreateDoseResponseCurveCommand,
)
from cellar.application.screening.create_readout_data import (
    CreateReadoutData,
    CreateReadoutDataCommand,
)
from cellar.application.screening.list_dose_response_enriched import (
    ListDoseResponseEnriched,
    ListDoseResponseEnrichedQuery,
)
from cellar.application.screening.list_readout_data_enriched import (
    ListReadoutDataEnriched,
    ListReadoutDataEnrichedQuery,
)
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.excluded_point_detail import ExcludedPointDetail
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.interface.dependencies import (
    AuthDep,
    BulkCreateReadoutDataDep,
    ClassifyDoseResponseCurveDep,
    CreateDoseResponseCurveDep,
    CreateReadoutDataDep,
    ListDoseResponseEnrichedDep,
    ListReadoutDataEnrichedDep,
    ReadoutCalculationEngineDep,
    RefitDoseResponseCurveDep,
    RefitDoseResponseCurvePreviewDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._intercept_response import (
    InterceptSpecResponse as InterceptSpecModel,
)
from cellar.interface.routes._intercept_response import (
    InterceptValueResponse as InterceptValueModel,
)

__all__ = ["InterceptSpecModel", "InterceptValueModel"]

router = APIRouter(prefix="/api/v1", tags=["readout-data"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ReadoutDataResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    well_id: uuid.UUID | None = None
    molecule_id: uuid.UUID | None = None
    registration_number: str | None = None
    molecule_name: str | None = None
    synonyms: list[str] = []
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    readout_definition_id: uuid.UUID
    value_numeric: float | None = None
    value_qualifier: str | None = None
    value_text: str | None = None
    is_outlier: bool
    is_computed: bool = False

    @classmethod
    def from_domain(
        cls,
        rd: ReadoutData,
        registration_number: str | None = None,
        molecule_name: str | None = None,
        synonyms: list[str] | None = None,
        batch_number: str | None = None,
    ) -> ReadoutDataResponse:
        return cls(
            id=rd.id,
            workspace_id=rd.workspace_id,
            run_id=rd.run_id,
            well_id=rd.well_id,
            molecule_id=rd.molecule_id,
            registration_number=registration_number,
            molecule_name=molecule_name,
            synonyms=synonyms or [],
            batch_id=rd.batch_id,
            batch_number=batch_number,
            readout_definition_id=rd.readout_definition_id,
            value_numeric=rd.value.value if rd.value else None,
            value_qualifier=rd.value.qualifier.value if rd.value else None,
            value_text=rd.value_text,
            is_outlier=rd.is_outlier,
            is_computed=rd.is_computed,
        )


class DoseResponseCurveResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    # Canonical reg id (e.g. "CV-00602") — primary label in compound tables.
    registration_number: str | None = None
    molecule_name: str | None = None
    # Vendor / external aliases for the molecule (e.g. ["Aspirin", "ASA"]).
    synonyms: list[str] = []
    smiles: str | None = None
    batch_id: uuid.UUID
    batch_number: str | None = None
    protocol_id: uuid.UUID
    run_id: uuid.UUID
    readout_definition_id: uuid.UUID
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
    fit_quality_warnings: list[str] = []
    # Per-spec intercepts derived from the same Hill fit. The first entry's
    # ``value`` mirrors ``fitted_value`` for back-compat.
    intercept_values: list[InterceptValueModel] = []

    @classmethod
    def from_domain(
        cls,
        c: DoseResponseCurve,
        *,
        registration_number: str | None = None,
        molecule_name: str | None = None,
        synonyms: list[str] | None = None,
        smiles: str | None = None,
        batch_number: str | None = None,
        dose_unit: str = "uM",
    ) -> DoseResponseCurveResponse:
        return cls(
            id=c.id,
            workspace_id=c.workspace_id,
            molecule_id=c.molecule_id,
            registration_number=registration_number,
            molecule_name=molecule_name,
            synonyms=synonyms or [],
            smiles=smiles,
            batch_id=c.batch_id,
            batch_number=batch_number,
            protocol_id=c.protocol_id,
            run_id=c.run_id,
            readout_definition_id=c.readout_definition_id,
            curve_type=c.curve_type.value,
            fitted_value=c.fitted_value,
            fitted_unit=dose_unit,
            hill_slope=c.hill_slope,
            top=c.top,
            bottom=c.bottom,
            r_squared=c.r_squared,
            confidence_interval_low=c.confidence_interval_low,
            confidence_interval_high=c.confidence_interval_high,
            num_points=c.num_points,
            curve_class=c.curve_class.value if c.curve_class else None,
            raw_data=c.raw_data or None,
            excluded_points=[
                ep.to_jsonb() if isinstance(ep, ExcludedPointDetail) else ep
                for ep in (c.excluded_points or [])
            ]
            or None,
            fit_quality_warnings=list(getattr(c, "fit_quality_warnings", []) or []),
            intercept_values=[
                InterceptValueModel.from_domain(iv)
                for iv in (getattr(c, "intercept_values", []) or [])
            ],
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
    errors: list[dict[str, Any]] = []


class CreateDoseResponseCurveRequest(BaseModel):
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    protocol_id: uuid.UUID
    run_id: uuid.UUID
    readout_definition_id: uuid.UUID
    curve_type: str
    fitted_value: float
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


class ExclusionPayloadEntryBody(BaseModel):
    """One entry in the Sprint 2 rich exclusion payload.

    Mirrors the application-layer ``ExclusionPayloadEntry`` dataclass — the
    route is a pure pass-through; the use case owns branching/validation.
    """

    idx: int | None
    source: Literal["manual", "auto_3sigma"]
    excluded: bool
    reason: Literal[
        "outlier",
        "instrument_artifact",
        "concentration_error",
        "contamination",
        "qc_failure",
        "other",
        "auto_3sigma",
    ]
    note: str | None = None
    concentration: float | None = None
    response: float | None = None


class RefitDoseResponseCurveRequest(BaseModel):
    excluded_point_indices: list[int] = Field(default_factory=list)
    hill_slope_constraint: str | None = None
    top_constraint: float | None = None
    bottom_constraint: float | None = None
    # Per-curve overrides (Phase B). Set ``override_<param>`` to True when the
    # client controls that param's mode end-to-end (Free/Range/Lock); leave
    # False to inherit the protocol's config for that param.
    override_top: bool = False
    top_constraint_min: float | None = None
    top_constraint_max: float | None = None
    override_bottom: bool = False
    bottom_constraint_min: float | None = None
    bottom_constraint_max: float | None = None
    override_hill: bool = False
    hill_slope_min: float | None = None
    hill_slope_max: float | None = None
    # When True, the use case suppresses the fitter's auto-3σ outlier pass so
    # user-driven point edits don't cascade into additional auto-exclusions.
    disable_auto_outliers: bool = False
    # ---- Sprint 2 rich payload + audit context --------------------------
    # When ``exclusions`` is provided the use case runs the Sprint 2 path:
    # persists rich ``ExcludedPointDetail`` entries, forces auto-outliers off
    # unconditionally, and writes a ``CURVE_POINT_EXCLUSION`` AuditOperation.
    # ``save_reason`` is REQUIRED by the use case when ``exclusions`` is set;
    # the use case raises ValidationError otherwise — the route just forwards.
    exclusions: list[ExclusionPayloadEntryBody] | None = None
    save_reason: Literal[
        "outlier",
        "instrument_artifact",
        "concentration_error",
        "contamination",
        "qc_failure",
        "other",
    ] | None = None
    save_note: str | None = None


class RefitPreviewRequest(BaseModel):
    """Compute-only preview refit request.

    The FE fires this on every draft toggle during point editing. Field name
    ``excluded_indices`` is kept short for FE friendliness; it maps to the
    use case command's ``excluded_point_indices``.
    """

    excluded_indices: list[int] = Field(default_factory=list)


class RefitPreviewResponse(BaseModel):
    """Mirror of ``PreviewRefitResult`` — the subset the FE needs to redraw
    the candidate curve during point editing."""

    fitted_value: float
    hill_slope: float
    top: float
    bottom: float
    r_squared: float
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    curve_class: str
    points_in_fit: int
    points_total: int


class ClassifyDoseResponseCurveRequest(BaseModel):
    curve_class: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/readout-data", response_model=ReadoutDataResponse, status_code=201)
async def create_readout_data(
    auth: AuthDep,
    body: CreateReadoutDataRequest,
    uc: CreateReadoutDataDep,
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
    uc: BulkCreateReadoutDataDep,
    engine: ReadoutCalculationEngineDep,
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

    # Trigger computation pipeline for each affected run
    run_ids = {item.run_id for item in body.items}
    for run_id in run_ids:
        await engine.compute_for_run(run_id, workspace_id=auth.workspace_id)

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
    uc: ListReadoutDataEnrichedDep,
) -> list[ReadoutDataResponse]:
    query = ListReadoutDataEnrichedQuery(workspace_id=auth.workspace_id, run_id=run_id)
    result = await uc(query, auth=auth)
    items = result_to_response(result)
    return [
        ReadoutDataResponse.from_domain(
            item.readout,
            registration_number=item.registration_number,
            molecule_name=item.molecule_name,
            synonyms=item.synonyms,
            batch_number=item.batch_number,
        )
        for item in items
    ]


@router.post("/dose-response-curves", response_model=DoseResponseCurveResponse, status_code=201)
async def create_dose_response_curve(
    auth: AuthDep,
    body: CreateDoseResponseCurveRequest,
    uc: CreateDoseResponseCurveDep,
) -> DoseResponseCurveResponse:
    cmd = CreateDoseResponseCurveCommand(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        batch_id=body.batch_id,
        protocol_id=body.protocol_id,
        run_id=body.run_id,
        readout_definition_id=body.readout_definition_id,
        curve_type=body.curve_type,
        fitted_value=body.fitted_value,
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
    uc: ListDoseResponseEnrichedDep,
) -> list[DoseResponseCurveResponse]:
    query = ListDoseResponseEnrichedQuery(workspace_id=auth.workspace_id, run_id=run_id)
    result = await uc(query, auth=auth)
    items = result_to_response(result)
    return [
        DoseResponseCurveResponse.from_domain(
            item.curve,
            registration_number=item.registration_number,
            molecule_name=item.molecule_name,
            synonyms=item.synonyms,
            smiles=item.smiles,
            batch_number=item.batch_number,
            dose_unit=item.dose_unit,
        )
        for item in items
    ]


@router.post("/dose-response-curves/{curve_id}/refit", response_model=DoseResponseCurveResponse)
async def refit_dose_response_curve(
    curve_id: uuid.UUID,
    body: RefitDoseResponseCurveRequest,
    auth: AuthDep,
    uc: RefitDoseResponseCurveDep,
) -> DoseResponseCurveResponse:
    from cellar.application.screening.refit_dose_response import (
        ExclusionPayloadEntry,
        RefitDoseResponseCurveCommand,
    )
    from cellar.domain.screening_assay.excluded_point_detail import (
        ExclusionReason,
        ExclusionSource,
    )

    exclusions: list[ExclusionPayloadEntry] | None = None
    if body.exclusions is not None:
        exclusions = [
            ExclusionPayloadEntry(
                idx=e.idx,
                source=ExclusionSource(e.source),
                excluded=e.excluded,
                reason=ExclusionReason(e.reason),
                note=e.note,
                concentration=e.concentration,
                response=e.response,
            )
            for e in body.exclusions
        ]
    save_reason = (
        ExclusionReason(body.save_reason) if body.save_reason is not None else None
    )

    result = await uc(
        RefitDoseResponseCurveCommand(
            workspace_id=auth.workspace_id,
            curve_id=curve_id,
            excluded_point_indices=body.excluded_point_indices,
            hill_slope_constraint=body.hill_slope_constraint,
            top_constraint=body.top_constraint,
            bottom_constraint=body.bottom_constraint,
            override_top=body.override_top,
            top_constraint_min=body.top_constraint_min,
            top_constraint_max=body.top_constraint_max,
            override_bottom=body.override_bottom,
            bottom_constraint_min=body.bottom_constraint_min,
            bottom_constraint_max=body.bottom_constraint_max,
            override_hill=body.override_hill,
            hill_slope_min=body.hill_slope_min,
            hill_slope_max=body.hill_slope_max,
            disable_auto_outliers=body.disable_auto_outliers,
            exclusions=exclusions,
            save_reason=save_reason,
            save_note=body.save_note,
        ),
        auth=auth,
    )
    return DoseResponseCurveResponse.from_domain(result_to_response(result))


@router.post(
    "/dose-response-curves/{curve_id}/refit-preview",
    response_model=RefitPreviewResponse,
    summary="Preview a dose-response refit without persisting (compute-only).",
)
async def refit_dose_response_curve_preview(
    curve_id: uuid.UUID,
    body: RefitPreviewRequest,
    auth: AuthDep,
    uc: RefitDoseResponseCurvePreviewDep,
) -> RefitPreviewResponse:
    """Compute-only preview refit.

    The FE calls this on every draft toggle during point editing; never
    persists, never audits, never auto-excludes. The existing /refit endpoint
    handles commit on Save.
    """
    from cellar.application.screening.refit_dose_response_preview import (
        PreviewRefitCommand,
    )

    result = await uc(
        PreviewRefitCommand(
            workspace_id=auth.workspace_id,
            curve_id=curve_id,
            excluded_point_indices=body.excluded_indices,
        ),
        auth=auth,
    )
    fitted = result_to_response(result)
    return RefitPreviewResponse(
        fitted_value=fitted.fitted_value,
        hill_slope=fitted.hill_slope,
        top=fitted.top,
        bottom=fitted.bottom,
        r_squared=fitted.r_squared,
        confidence_interval_low=fitted.confidence_interval_low,
        confidence_interval_high=fitted.confidence_interval_high,
        curve_class=fitted.curve_class,
        points_in_fit=fitted.points_in_fit,
        points_total=fitted.points_total,
    )


@router.patch(
    "/dose-response-curves/{curve_id}/classify", response_model=DoseResponseCurveResponse
)
async def classify_dose_response_curve(
    curve_id: uuid.UUID,
    body: ClassifyDoseResponseCurveRequest,
    auth: AuthDep,
    uc: ClassifyDoseResponseCurveDep,
) -> DoseResponseCurveResponse:
    from cellar.application.screening.classify_dose_response import (
        ClassifyDoseResponseCurveCommand,
    )

    result = await uc(
        ClassifyDoseResponseCurveCommand(
            workspace_id=auth.workspace_id,
            curve_id=curve_id,
            curve_class=body.curve_class,
        ),
        auth=auth,
    )
    return DoseResponseCurveResponse.from_domain(result_to_response(result))
