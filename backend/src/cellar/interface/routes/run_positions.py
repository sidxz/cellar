"""Edit a run's positions after an instrument import: label, note, role, batch, concentration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cellar.application.screening.relabel_run_positions import (
    RelabelResult,
    RelabelRunPositionsCommand,
)
from cellar.domain.screening_assay.run import PositionEdit, PositionValues
from cellar.domain.shared.enums import WellType
from cellar.interface.dependencies import AuthDep, RelabelRunPositionsDep
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
    positions: list[PositionEditRequest] = Field(min_length=1)
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
