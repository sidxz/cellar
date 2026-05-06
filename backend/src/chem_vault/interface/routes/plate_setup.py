"""Plate setup and simplified readout import routes for screening runs."""

from __future__ import annotations

import uuid
from typing import Annotated

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
    # Doses are interpreted in the run's protocol.dose_unit — no per-request unit.
    concentration_series: list[float] | None = None


class SetUpRunPlateResponse(BaseModel):
    plate_id: uuid.UUID
    wells_created: int
    compounds_assigned: int
    unresolved: list[str]


class PlateMapWellModel(BaseModel):
    well_id: uuid.UUID
    position: str
    row: str
    column: int
    well_type: str
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    synonyms: list[str] = []
    smiles: str | None = None
    # Dose value in the protocol's dose_unit (carried at the response level
    # so the client does not need to look up the protocol separately).
    dose: float | None = None


class PlateMapSummaryModel(BaseModel):
    total_wells: int
    sample_wells: int
    control_wells: int
    compounds: int
    concentrations_per_compound: int
    replicates: int


class PlateData(BaseModel):
    plate_id: uuid.UUID
    plate_number: int
    format: str
    wells: list[PlateMapWellModel]
    summary: PlateMapSummaryModel


class PlateMapResponse(BaseModel):
    run_id: uuid.UUID
    # The protocol's dose_unit. All `wells[].dose` values are in this unit.
    dose_unit: str
    plates: list[PlateData]


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
    """Upload a plate map file (CSV or XLSX) and return parsed compound assignments.

    Supported layouts:
    - Well-level: ``Well, Compound`` columns — one row per well.
    - Row-range: ``Compound, Start Row, End Row`` columns — compound assigned
      to all wells in those rows.
    """
    content = await file.read()
    result = await uc(content, filename=file.filename or "", auth=auth)
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

    plates_data: list[PlateData] = []
    for plate in data.plates:
        well_entries = [
            PlateMapWellModel(
                well_id=w.well_id,
                position=w.position,
                row=w.row,
                column=w.column,
                well_type=w.well_type,
                batch_id=w.batch_id,
                batch_number=w.batch_number,
                molecule_id=w.molecule_id,
                molecule_name=w.molecule_name,
                synonyms=list(w.synonyms),
                smiles=w.smiles,
                dose=w.dose,
            )
            for w in plate.wells
        ]
        summary = plate.summary
        plates_data.append(
            PlateData(
                plate_id=plate.plate_id,
                plate_number=plate.plate_number,
                format=plate.format,
                wells=well_entries,
                summary=PlateMapSummaryModel(
                    total_wells=summary.total_wells if summary else 0,
                    sample_wells=summary.sample_wells if summary else 0,
                    control_wells=summary.control_wells if summary else 0,
                    compounds=summary.compounds if summary else 0,
                    concentrations_per_compound=(
                        summary.concentrations_per_compound if summary else 0
                    ),
                    replicates=summary.replicates if summary else 0,
                ),
            )
        )

    return PlateMapResponse(
        run_id=run_id, dose_unit=data.dose_unit, plates=plates_data
    )


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
    """Import readout data from a CSV or XLSX into a run that already has wells set up.

    Wells must have been created via the plate-setup endpoint first.
    After import, the readout calculation engine runs automatically to
    normalize, aggregate, and fit dose-response curves.

    Supported layouts:
    - Single-value: ``Well, Value`` columns with ``readout_definition_id`` query param.
    - Multi-column: ``Well, <ReadoutDefName1>, <ReadoutDefName2>, ...`` — headers
      matched case-insensitively to readout definition names.
    """
    content = await file.read()

    cmd = ImportRunReadoutsCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        file_content=content,
        filename=file.filename or "",
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
