"""Plate setup and simplified readout import routes for screening runs."""

from __future__ import annotations

import contextlib
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel, Field

from cellar.application.screening.fit_dose_response import FitOverrides
from cellar.application.screening.get_plate_map import GetPlateMapQuery
from cellar.application.screening.import_run_readouts import (
    ImportRunReadoutsCommand,
    ImportRunReadoutsResult,
)
from cellar.application.screening.link_run_plate import (
    LinkRunPlateCommand,
    RunPlateLink,
    UnlinkRunPlateCommand,
)
from cellar.application.screening.plate_setup import (
    CompoundAssignment,
    ParsedPlateMap,
    SetUpRunPlateCommand,
)
from cellar.application.shared.grid_plate_reshaper import reshape_grid_to_well_value_csv
from cellar.domain.screening_assay.enums import HillSlopeConstraint
from cellar.domain.shared.errors import ValidationError
from cellar.interface.dependencies import (
    AuthDep,
    GetPlateMapDep,
    ImportRunReadoutsDep,
    LinkRunPlateDep,
    ParsePlateMapFileDep,
    ReadoutCalculationEngineDep,
    SetUpRunPlateDep,
    UnlinkRunPlateDep,
)
from cellar.interface.error_handlers import result_to_response

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
    # Physical inventory plate this run plate was run on — all null when unlinked.
    registered_plate_id: uuid.UUID | None = None
    registered_plate_barcode: str | None = None
    registered_plate_label: str | None = None


class PlateMapResponse(BaseModel):
    run_id: uuid.UUID
    # The protocol's dose_unit. All `wells[].dose` values are in this unit.
    dose_unit: str
    plates: list[PlateData]


class LinkRunPlateBody(BaseModel):
    # A barcode or a plate label — resolved server-side (no UUIDs in the UI).
    barcode: str = Field(min_length=1, max_length=100)


class RunPlateLinkResponse(BaseModel):
    plate_id: uuid.UUID
    registered_plate_id: uuid.UUID | None = None
    barcode: str | None = None
    plate_label: str | None = None

    @classmethod
    def from_domain(cls, link: RunPlateLink) -> RunPlateLinkResponse:
        return cls(
            plate_id=link.plate_id,
            registered_plate_id=link.registered_plate_id,
            barcode=link.barcode,
            plate_label=link.plate_label,
        )


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
                registered_plate_id=plate.registered_plate_id,
                registered_plate_barcode=plate.registered_plate_barcode,
                registered_plate_label=plate.registered_plate_label,
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

    return PlateMapResponse(run_id=run_id, dose_unit=data.dose_unit, plates=plates_data)


@router.post("/runs/{run_id}/plates/{plate_id}:link", response_model=RunPlateLinkResponse)
async def link_run_plate(
    run_id: uuid.UUID,
    plate_id: uuid.UUID,
    auth: AuthDep,
    body: LinkRunPlateBody,
    uc: LinkRunPlateDep,
) -> RunPlateLinkResponse:
    """Point a run plate at the physical inventory plate it was run on.

    ``barcode`` accepts a barcode or a plate label. Relinking overwrites.
    """
    result = await uc(
        LinkRunPlateCommand(
            workspace_id=auth.workspace_id,
            run_id=run_id,
            plate_id=plate_id,
            barcode=body.barcode,
        ),
        auth=auth,
    )
    return RunPlateLinkResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/plates/{plate_id}:unlink", response_model=RunPlateLinkResponse)
async def unlink_run_plate(
    run_id: uuid.UUID,
    plate_id: uuid.UUID,
    auth: AuthDep,
    uc: UnlinkRunPlateDep,
) -> RunPlateLinkResponse:
    """Clear a run plate's inventory link."""
    result = await uc(
        UnlinkRunPlateCommand(workspace_id=auth.workspace_id, run_id=run_id, plate_id=plate_id),
        auth=auth,
    )
    return RunPlateLinkResponse.from_domain(result_to_response(result))


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
    layout: Annotated[str, Query()] = "long",
) -> ImportReadoutsResponse:
    """Import readout data from a CSV or XLSX into a run that already has wells set up.

    Wells must have been created via the plate-setup endpoint first.
    After import, the readout calculation engine runs automatically to
    normalize, aggregate, and fit dose-response curves.

    Supported layouts:
    - Single-value: ``Well, Value`` columns with ``readout_definition_id`` query param.
    - Multi-column: ``Well, <ReadoutDefName1>, <ReadoutDefName2>, ...`` — headers
      matched case-insensitively to readout definition names.
    - Grid (``layout=grid``): a plate matrix (column numbers across the top, row
      letters down the side) for a single ``readout_definition_id``; reshaped to
      ``Well, Value`` before import.
    """
    content = await file.read()
    filename = file.filename or ""

    # Grid layout: reshape the plate matrix into the Well,Value long format the
    # importer already understands. A grid carries a single readout, so the
    # readout definition must be supplied.
    if layout == "grid":
        if readout_definition_id is None:
            raise ValidationError(
                "Grid layout requires a readout to import into (readout_definition_id)."
            )
        content = reshape_grid_to_well_value_csv(content, filename)
        filename = "grid.csv"

    cmd = ImportRunReadoutsCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        file_content=content,
        filename=filename,
        readout_definition_id=readout_definition_id,
    )
    result = await import_uc(cmd, auth=auth)
    import_result: ImportRunReadoutsResult = result_to_response(result)

    # Auto-trigger calculation pipeline (best-effort — don't fail the import)
    if import_result.readouts_created > 0:
        # Calculation errors don't fail the import (best-effort).
        with contextlib.suppress(Exception):
            await calc_engine.compute_for_run(run_id, workspace_id=auth.workspace_id)

    return ImportReadoutsResponse(
        total_rows=import_result.total_rows,
        matched=import_result.matched,
        unmatched=import_result.unmatched,
        readouts_created=import_result.readouts_created,
    )


# ---------------------------------------------------------------------------
# Recompute readouts (re-runs normalization + replicate aggregation +
# calculated readouts + dose-response fitting against existing raw data)
# ---------------------------------------------------------------------------


class RecomputeRunResponse(BaseModel):
    computed_readouts: int
    fit_warnings: list[str] = []


class RecomputeRunRequest(BaseModel):
    """Optional per-recompute fit constraint overrides.

    Empty body (or all flags False) → use the protocol's configured
    DoseResponseConfig. When ``override_<param>`` is True the popover is
    authoritative for that param on this recompute (Free / Range / Lock).
    Overrides are NOT persisted on the protocol or run.
    """

    override_top: bool = False
    top_constraint: float | None = None
    top_constraint_min: float | None = None
    top_constraint_max: float | None = None
    override_bottom: bool = False
    bottom_constraint: float | None = None
    bottom_constraint_min: float | None = None
    bottom_constraint_max: float | None = None
    override_hill: bool = False
    hill_slope_constraint: HillSlopeConstraint | None = None
    hill_slope_min: float | None = None
    hill_slope_max: float | None = None


@router.post(
    "/runs/{run_id}/recompute",
    response_model=RecomputeRunResponse,
    tags=["screening-runs"],
)
async def recompute_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    engine: ReadoutCalculationEngineDep,
    body: RecomputeRunRequest | None = None,
) -> RecomputeRunResponse:
    """Re-run the readout calculation pipeline on a run's existing raw data.

    Idempotent: the engine deletes previously-computed readouts and
    dose-response curves before recomputing. Useful when a normalization
    formula or computed readout definition has changed and the persisted
    computed values need to be regenerated without re-importing the file.

    The optional body allows transient per-run constraint overrides on the
    dose-response fits (top/bottom plateau bounds, hill slope). Overrides
    apply to this recompute pass only and are not stored.
    """
    overrides = (
        FitOverrides(
            override_top=body.override_top,
            top=body.top_constraint,
            top_min=body.top_constraint_min,
            top_max=body.top_constraint_max,
            override_bottom=body.override_bottom,
            bottom=body.bottom_constraint,
            bottom_min=body.bottom_constraint_min,
            bottom_max=body.bottom_constraint_max,
            override_hill=body.override_hill,
            hill_slope=body.hill_slope_constraint,
            hill_slope_min=body.hill_slope_min,
            hill_slope_max=body.hill_slope_max,
        )
        if body is not None and not _all_none(body)
        else None
    )
    result = await engine.compute_for_run(
        run_id, workspace_id=auth.workspace_id, fit_overrides=overrides
    )
    outcome = result_to_response(result)
    return RecomputeRunResponse(
        computed_readouts=len(outcome.computed_readouts),
        fit_warnings=outcome.fit_warnings,
    )


def _all_none(body: RecomputeRunRequest) -> bool:
    """No-op detector: if no override flag is set, the body has nothing to apply."""
    return not (body.override_top or body.override_bottom or body.override_hill)
