"""Plate setup and simplified readout import routes for screening runs."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

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
from chem_vault.interface.dependencies import (
    AuthDep,
    ImportRunReadoutsDep,
    ParsePlateMapFileDep,
    ReadoutCalculationEngineDep,
    SetUpRunPlateDep,
    UoWDep,
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
    uow: UoWDep,
) -> PlateMapResponse:
    """Return structured plate map data with molecule names and concentrations.

    Loads the run's plates and wells, then batch-resolves molecule names from
    the chemical registration store for display.
    """
    from sqlalchemy import select

    from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel
    from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel
    from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
        PlateModel,
        RunModel,
        WellModel,
    )

    async with uow:
        # Load run (workspace scoped)
        run_stmt = select(RunModel).where(
            RunModel.id == run_id,
            RunModel.workspace_id == auth.workspace_id,
        )
        run_row = await uow.session.execute(run_stmt)
        run_model = run_row.scalar_one_or_none()
        if run_model is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Run not found")

        # Load plates for this run
        plates_stmt = select(PlateModel).where(PlateModel.run_id == run_id)
        plates_result = await uow.session.execute(plates_stmt)
        plates = plates_result.scalars().all()

        plate_ids = [p.id for p in plates]

        # Load wells for all plates
        wells: list[WellModel] = []
        if plate_ids:
            wells_stmt = select(WellModel).where(WellModel.plate_id.in_(plate_ids))
            wells_result = await uow.session.execute(wells_stmt)
            wells = list(wells_result.scalars().all())

        # Batch-resolve batch → molecule_id
        batch_ids = list({w.batch_id for w in wells if w.batch_id is not None})
        batch_to_mol: dict[uuid.UUID, uuid.UUID] = {}
        mol_names: dict[uuid.UUID, str] = {}

        if batch_ids:
            batch_stmt = select(BatchModel.id, BatchModel.molecule_id).where(
                BatchModel.id.in_(batch_ids)
            )
            batch_rows = await uow.session.execute(batch_stmt)
            batch_to_mol = {row[0]: row[1] for row in batch_rows}

            mol_ids = list(set(batch_to_mol.values()))
            if mol_ids:
                mol_stmt = select(MoleculeModel.id, MoleculeModel.name).where(
                    MoleculeModel.id.in_(mol_ids)
                )
                mol_rows = await uow.session.execute(mol_stmt)
                mol_names = {row[0]: row[1] for row in mol_rows}

        # Build plate_id → wells mapping
        plate_wells: dict[uuid.UUID, list[WellModel]] = {p.id: [] for p in plates}
        for w in wells:
            plate_wells[w.plate_id].append(w)

        plates_data = []
        for plate in sorted(plates, key=lambda p: p.plate_number):
            well_entries = []
            for well in sorted(plate_wells[plate.id], key=lambda w: (w.row, w.column)):
                molecule_id = batch_to_mol.get(well.batch_id) if well.batch_id else None
                conc_value: float | None = well.concentration_value
                conc_unit: str | None = well.concentration_unit

                well_entries.append(
                    WellMapEntry(
                        well_id=well.id,
                        row=well.row,
                        column=well.column,
                        well_type=well.well_type,
                        batch_id=well.batch_id,
                        molecule_id=molecule_id,
                        molecule_name=mol_names.get(molecule_id) if molecule_id else None,
                        concentration_value=conc_value,
                        concentration_unit=conc_unit,
                    ).model_dump()
                )
            plates_data.append(
                {
                    "plate_id": str(plate.id),
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
