"""Plate setup and simplified readout import routes for screening runs."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

from chem_vault.application.screening.fit_curves_for_run import FitCurvesForRun, FitCurvesForRunQuery
from chem_vault.application.screening.get_plate_map import GetPlateMap, GetPlateMapQuery
from chem_vault.application.screening.import_run_readouts import (
    ImportRunReadouts,
    ImportRunReadoutsCommand,
    ImportRunReadoutsResult,
)
from chem_vault.application.screening.plate_setup import (
    CompoundAssignment,
    ParsePlateMapFile,
    ParsedPlateMap,
    SetUpRunPlate,
    SetUpRunPlateCommand,
)
from chem_vault.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from chem_vault.domain.shared.errors import DomainError
from chem_vault.interface.dependencies import (
    AuthDep,
    FitCurvesForRunDep,
    GetPlateMapDep,
    ImportRunReadoutsDep,
    ParsePlateMapFileDep,
    ReadoutCalculationEngineDep,
    SetUpRunPlateDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["plate-setup"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CompoundAssignmentResponse(BaseModel):
    molecule_ref: str
    batch_ref: str | None = None
    well_positions: list[str]


class ParsePlateMapResponse(BaseModel):
    assignments: list[CompoundAssignmentResponse]
    unresolved: list[str]
    row_count: int


class SetUpRunPlateRequest(BaseModel):
    plate_number: int = 1
    compound_assignments: list[CompoundAssignmentResponse]
    concentration_series: list[float] | None = None
    concentration_unit: str = "nM"


class SetUpRunPlateResponse(BaseModel):
    plate_id: uuid.UUID
    wells_created: int
    compounds_assigned: int
    unresolved: list[str]


class WellMapEntry(BaseModel):
    well_id: uuid.UUID
    row: str
    column: int
    well_type: str
    batch_id: uuid.UUID | None = None
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None


class PlateMapResponse(BaseModel):
    run_id: uuid.UUID
    plates: list[dict[str, Any]]


class ImportReadoutsResponse(BaseModel):
    total_rows: int
    matched: int
    unmatched: int
    readouts_created: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/runs/{run_id}/plate-setup/parse",
    response_model=ParsePlateMapResponse,
    status_code=200,
)
async def parse_plate_map_file(
    run_id: uuid.UUID,
    auth: AuthDep,
    file: Annotated[UploadFile, File()],
    uc: ParsePlateMapFileDep,
) -> ParsePlateMapResponse:
    """Upload a plate map CSV and return parsed compound assignments.

    Supported formats:
    - Well-level: ``Well, Compound`` columns — one row per well.
    - Row-range: ``Compound, Start Row, End Row`` columns — compound assigned
      to all wells in those rows.
    """
    content = await file.read()
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        csv_text = content.decode("latin-1")

    result = await uc(csv_text, auth=auth)
    parsed: ParsedPlateMap = result_to_response(result)

    return ParsePlateMapResponse(
        assignments=[
            CompoundAssignmentResponse(
                molecule_ref=a.molecule_ref,
                batch_ref=a.batch_ref,
                well_positions=a.well_positions,
            )
            for a in parsed.assignments
        ],
        unresolved=parsed.unresolved,
        row_count=parsed.row_count,
    )


@router.post(
    "/runs/{run_id}/plate-setup",
    response_model=SetUpRunPlateResponse,
    status_code=201,
)
async def set_up_run_plate(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: SetUpRunPlateRequest,
    uc: SetUpRunPlateDep,
) -> SetUpRunPlateResponse:
    """Create wells on a run plate from compound assignments."""
    assignments = [
        CompoundAssignment(
            molecule_ref=a.molecule_ref,
            batch_ref=a.batch_ref,
            well_positions=a.well_positions,
        )
        for a in body.compound_assignments
    ]

    cmd = SetUpRunPlateCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        plate_number=body.plate_number,
        compound_assignments=assignments,
        concentration_series=body.concentration_series,
        concentration_unit=body.concentration_unit,
    )
    result = await uc(cmd, auth=auth)
    data = result_to_response(result)

    return SetUpRunPlateResponse(
        plate_id=data["plate_id"],
        wells_created=data["wells_created"],
        compounds_assigned=data["compounds_assigned"],
        unresolved=data["unresolved"],
    )


@router.get("/runs/{run_id}/plate-map", response_model=PlateMapResponse)
async def get_plate_map(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: GetPlateMapDep,
) -> PlateMapResponse:
    """Return structured plate map data with molecule names and concentrations.

    Loads the run's plates and wells, then batch-resolves molecule names from
    the chemical registration store for display.
    """
    result = await uc(
        GetPlateMapQuery(workspace_id=auth.workspace_id, run_id=run_id),
        auth=auth,
    )
    data = result_to_response(result)

    plates_data = []
    for plate in data.plates:
        well_entries = [
            WellMapEntry(
                well_id=w.well_id,
                row=w.row,
                column=w.column,
                well_type=w.well_type,
                batch_id=w.batch_id,
                molecule_id=w.molecule_id,
                molecule_name=w.molecule_name,
                concentration_value=w.concentration_value,
                concentration_unit=w.concentration_unit,
            ).model_dump()
            for w in plate.wells
        ]
        plates_data.append(
            {
                "plate_id": str(plate.plate_id),
                "plate_number": plate.plate_number,
                "wells": well_entries,
            }
        )

    return PlateMapResponse(run_id=run_id, plates=plates_data)


@router.post(
    "/runs/{run_id}/import-readouts",
    response_model=ImportReadoutsResponse,
    status_code=201,
)
async def import_run_readouts(
    run_id: uuid.UUID,
    auth: AuthDep,
    file: Annotated[UploadFile, File()],
    import_uc: ImportRunReadoutsDep,
    calc_engine: ReadoutCalculationEngineDep,
    readout_definition_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ImportReadoutsResponse:
    """Import readout data from a CSV into a run that already has wells set up.

    Wells must have been created via the plate-setup endpoint first.
    After import, the readout calculation engine runs automatically to
    normalize, aggregate, and fit dose-response curves.

    Supported CSV formats:
    - Single-value: ``Well, Value`` columns with ``readout_definition_id`` query param.
    - Multi-column: ``Well, <ReadoutDefName1>, <ReadoutDefName2>, ...`` — headers
      matched case-insensitively to readout definition names.
    """
    content = await file.read()

    cmd = ImportRunReadoutsCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        csv_content=content,
        readout_definition_id=readout_definition_id,
    )
    result = await import_uc(cmd, auth=auth)
    import_result: ImportRunReadoutsResult = result_to_response(result)

    # Auto-trigger calculation pipeline (best-effort — don't fail the import)
    if import_result.readouts_created > 0:
        try:
            await calc_engine.compute_for_run(run_id, workspace_id=auth.workspace_id)
        except Exception:
            pass  # Calculation errors don't fail the import

    return ImportReadoutsResponse(
        total_rows=import_result.total_rows,
        matched=import_result.matched,
        unmatched=import_result.unmatched,
        readouts_created=import_result.readouts_created,
    )


# ---------------------------------------------------------------------------
# Compute / re-fit dose-response curves
# ---------------------------------------------------------------------------


class FitWarning(BaseModel):
    molecule_name: str | None = None
    reason: str


class FitCurvesResponse(BaseModel):
    curves_fitted: int
    warnings: list[FitWarning] = []


@router.post(
    "/runs/{run_id}/fit-curves",
    response_model=FitCurvesResponse,
    tags=["screening-runs"],
)
async def fit_curves_for_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: FitCurvesForRunDep,
) -> FitCurvesResponse:
    """Trigger dose-response curve fitting for a run.

    Loads run (with wells), protocol, and readout data, then fits 4PL
    curves.  Idempotent: deletes previous curves before re-fitting.
    """
    try:
        result = await uc(
            FitCurvesForRunQuery(workspace_id=auth.workspace_id, run_id=run_id),
            auth=auth,
        )
        curves = result_to_response(result)
        return FitCurvesResponse(curves_fitted=len(curves))
    except DomainError as exc:
        return FitCurvesResponse(
            curves_fitted=0,
            warnings=[FitWarning(reason=str(exc))],
        )
