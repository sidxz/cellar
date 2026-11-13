"""Edit a run's positions after an instrument import: label, note, role, batch, concentration.

Also reads a labelling layout file for the labelling table to fill itself from.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

from cellar.application.screening.instrument_export import MAX_INSTRUMENT_FILE_BYTES
from cellar.application.screening.relabel_run_positions import (
    RelabelResult,
    RelabelRunPositionsCommand,
)
from cellar.application.screening.resolve_layout_file import (
    MAX_LAYOUT_ROWS,
    LayoutCompound,
    LayoutFile,
    LayoutRow,
    ResolveLayoutFileQuery,
)
from cellar.domain.screening_assay.run import PositionEdit, PositionValues
from cellar.domain.shared.enums import WellType
from cellar.interface.dependencies import AuthDep, RelabelRunPositionsDep, ResolveLayoutFileDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["run-positions"])


class PositionValuesModel(BaseModel):
    label: str = Field("", max_length=200)
    note: str = Field("", max_length=1000)
    well_type: WellType
    batch_id: uuid.UUID | None
    # In the protocol's dose unit.
    dose: float | None = Field(None, ge=0, allow_inf_nan=False)

    def to_domain(self) -> PositionValues:
        return PositionValues(
            label=self.label,
            note=self.note,
            well_type=self.well_type,
            batch_id=self.batch_id,
            dose=self.dose,
        )


class PositionEditRequest(BaseModel):
    well_id: uuid.UUID
    # The values the user started from; a save is refused when they no longer match.
    expected: PositionValuesModel
    new: PositionValuesModel


class RelabelPositionsRequest(BaseModel):
    # At most as many positions as a layout file can fill; the run refuses any not on it.
    positions: list[PositionEditRequest] = Field(min_length=1, max_length=MAX_LAYOUT_ROWS)
    # Required when the run is completed or approved.
    reason: str | None = Field(None, max_length=500)


class RelabelPositionsResponse(BaseModel):
    positions_changed: int
    readouts_repointed: int
    recalculated: bool
    compute_warning: str | None

    @classmethod
    def from_domain(cls, out: RelabelResult) -> RelabelPositionsResponse:
        return cls(
            positions_changed=out.positions_changed,
            readouts_repointed=out.readouts_repointed,
            recalculated=out.recalculated,
            compute_warning=out.compute_warning,
        )


@router.post("/runs/{run_id}/relabel-positions", response_model=RelabelPositionsResponse)
async def relabel_run_positions(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: RelabelPositionsRequest,
    uc: RelabelRunPositionsDep,
) -> RelabelPositionsResponse:
    """Change positions' label, note, role, batch or concentration, with an audit record."""
    cmd = RelabelRunPositionsCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        edits=tuple(
            PositionEdit(p.well_id, p.expected.to_domain(), p.new.to_domain())
            for p in body.positions
        ),
        reason=body.reason,
    )
    result = await uc(cmd, auth=auth)
    return RelabelPositionsResponse.from_domain(result_to_response(result))


class LayoutCompoundModel(BaseModel):
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    batch_id: uuid.UUID | None
    batch_number: str | None
    # The compound has several batches and the file named none.
    needs_batch_choice: bool

    @classmethod
    def from_domain(cls, c: LayoutCompound) -> LayoutCompoundModel:
        return cls(
            molecule_id=c.molecule_id,
            molecule_name=c.molecule_name,
            registration_number=c.registration_number,
            batch_id=c.batch_id,
            batch_number=c.batch_number,
            needs_batch_choice=c.needs_batch_choice,
        )


class LayoutRowModel(BaseModel):
    # The Position cell, trimmed; the browser matches it to the table's position labels.
    position: str
    # A value is null when its cell was empty, its column absent, or it had a problem.
    label: str | None
    note: str | None
    well_type: str | None
    dose: float | None
    use: bool | None
    compound: LayoutCompoundModel | None
    problems: list[str]

    @classmethod
    def from_domain(cls, r: LayoutRow) -> LayoutRowModel:
        return cls(
            position=r.position,
            label=r.label,
            note=r.note,
            well_type=r.well_type.value if r.well_type is not None else None,
            dose=r.dose,
            use=r.use,
            compound=LayoutCompoundModel.from_domain(r.compound) if r.compound else None,
            problems=list(r.problems),
        )


class LayoutFileResponse(BaseModel):
    rows: list[LayoutRowModel]
    unrecognised_columns: list[str]
    # Role, compound, batch and concentration cannot change on this run, and the file
    # had cells in those columns: they were ignored.
    calculated_columns_ignored: bool

    @classmethod
    def from_domain(cls, f: LayoutFile) -> LayoutFileResponse:
        return cls(
            rows=[LayoutRowModel.from_domain(r) for r in f.rows],
            unrecognised_columns=list(f.unrecognised_columns),
            calculated_columns_ignored=f.calculated_columns_ignored,
        )


@router.post("/runs/{run_id}/resolve-layout-file", response_model=LayoutFileResponse)
async def resolve_layout_file(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: ResolveLayoutFileDep,
    file: Annotated[UploadFile, File()],
) -> LayoutFileResponse:
    """Read a labelling layout file and resolve its compounds and batches. Writes nothing."""
    query = ResolveLayoutFileQuery(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        filename=file.filename or "upload",
        # One byte past the limit is enough for the query to refuse the file.
        content=await file.read(MAX_INSTRUMENT_FILE_BYTES + 1),
    )
    result = await uc(query, auth=auth)
    return LayoutFileResponse.from_domain(result_to_response(result))
