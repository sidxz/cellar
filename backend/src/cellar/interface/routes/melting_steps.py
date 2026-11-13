"""A run's melting analysis, and adding and reviewing its melting steps."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cellar.application.screening.get_melting_analysis import (
    ChannelStepCheck,
    GetMeltingAnalysisQuery,
    MeltingAnalysis,
    WindowAnalysis,
)
from cellar.application.screening.manage_melting_steps import (
    AddMeltingStepCommand,
    MeltingStepChange,
    ReviewMeltingStepCommand,
)
from cellar.domain.screening_assay.melt_window import PositionWindowResult
from cellar.domain.screening_assay.melting_step import (
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.interface.dependencies import (
    AddMeltingStepDep,
    AuthDep,
    GetMeltingAnalysisDep,
    ReviewMeltingStepDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["melting-steps"])


class MeltingStepModel(BaseModel):
    id: uuid.UUID
    well_id: uuid.UUID
    channel_key: str
    source: MeltingStepSource
    value: float
    instrument_value: float | None
    instrument_label: str | None
    status: MeltingStepStatus
    reason: str | None
    changed_by: uuid.UUID | None
    changed_at: datetime | None
    version: int

    @classmethod
    def from_domain(cls, s: MeltingStep) -> MeltingStepModel:
        return cls(
            id=s.id,
            well_id=s.well_id,
            channel_key=s.channel_key,
            source=s.source,
            value=s.value,
            instrument_value=s.instrument_value,
            instrument_label=s.instrument_label,
            status=s.status,
            reason=s.reason,
            changed_by=s.changed_by,
            changed_at=s.changed_at,
            version=s.version,
        )


class MeltWindowPositionModel(BaseModel):
    well_id: uuid.UUID
    tm: float | None
    delta_tm: float | None
    flags: list[str]

    @classmethod
    def from_domain(cls, p: PositionWindowResult) -> MeltWindowPositionModel:
        return cls(
            well_id=p.well_id, tm=p.tm, delta_tm=p.delta_tm, flags=[f.value for f in p.flags]
        )


class MeltWindowModel(BaseModel):
    window: str
    channel_key: str
    low: float
    high: float
    tm_readout_id: uuid.UUID | None
    delta_tm_readout_id: uuid.UUID | None
    reference_tm: float | None
    reference_count: int
    flags: list[str]
    positions: list[MeltWindowPositionModel]

    @classmethod
    def from_domain(cls, w: WindowAnalysis) -> MeltWindowModel:
        return cls(
            window=w.window,
            channel_key=w.channel_key,
            low=w.low,
            high=w.high,
            tm_readout_id=w.tm_readout_id,
            delta_tm_readout_id=w.delta_tm_readout_id,
            reference_tm=w.result.reference_tm,
            reference_count=w.result.reference_count,
            flags=[f.value for f in w.result.flags],
            positions=[MeltWindowPositionModel.from_domain(p) for p in w.result.positions],
        )


class StepCheckModel(BaseModel):
    channel_key: str
    # Positions whose number of counted steps differs from the references'.
    differs: list[uuid.UUID]
    # The references disagree among themselves, so no position is compared.
    references_differ: bool

    @classmethod
    def from_domain(cls, c: ChannelStepCheck) -> StepCheckModel:
        return cls(
            channel_key=c.channel_key,
            differs=sorted(c.check.differs, key=str),
            references_differ=c.check.references_differ,
        )


class MeltingAnalysisResponse(BaseModel):
    run_id: uuid.UUID
    # Why steps cannot be changed on this run; null when they can.
    edit_refusal: str | None
    steps: list[MeltingStepModel]
    windows: list[MeltWindowModel]
    step_checks: list[StepCheckModel]

    @classmethod
    def from_domain(cls, a: MeltingAnalysis) -> MeltingAnalysisResponse:
        return cls(
            run_id=a.run_id,
            edit_refusal=a.edit_refusal,
            steps=[MeltingStepModel.from_domain(s) for s in a.steps],
            windows=[MeltWindowModel.from_domain(w) for w in a.windows],
            step_checks=[StepCheckModel.from_domain(c) for c in a.step_checks],
        )


class AddMeltingStepRequest(BaseModel):
    well_id: uuid.UUID
    channel_key: str = Field(min_length=1)
    value: float = Field(allow_inf_nan=False)
    reason: str | None = Field(None, max_length=500)


class ReviewMeltingStepRequest(BaseModel):
    # The version the user read; a save over someone else's change is refused.
    expected_version: int = Field(ge=1)
    status: MeltingStepStatus
    value: float = Field(allow_inf_nan=False)
    reason: str | None = Field(None, max_length=500)


class MeltingStepChangeResponse(BaseModel):
    step: MeltingStepModel
    recalculated: bool
    compute_warning: str | None

    @classmethod
    def from_domain(cls, c: MeltingStepChange) -> MeltingStepChangeResponse:
        return cls(
            step=MeltingStepModel.from_domain(c.step),
            recalculated=c.recalculated,
            compute_warning=c.compute_warning,
        )


@router.get("/runs/{run_id}/melting-analysis", response_model=MeltingAnalysisResponse)
async def get_melting_analysis(
    run_id: uuid.UUID, auth: AuthDep, uc: GetMeltingAnalysisDep
) -> MeltingAnalysisResponse:
    """The run's melting steps, its temperature windows' Tm and ΔTm, and step-count checks."""
    result = await uc(
        GetMeltingAnalysisQuery(workspace_id=auth.workspace_id, run_id=run_id), auth=auth
    )
    return MeltingAnalysisResponse.from_domain(result_to_response(result))


@router.post(
    "/runs/{run_id}/melting-steps", response_model=MeltingStepChangeResponse, status_code=201
)
async def add_melting_step(
    run_id: uuid.UUID, body: AddMeltingStepRequest, auth: AuthDep, uc: AddMeltingStepDep
) -> MeltingStepChangeResponse:
    """Add a hand-made melting step to a position, then recalculate the run."""
    cmd = AddMeltingStepCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        well_id=body.well_id,
        channel_key=body.channel_key,
        value=body.value,
        reason=body.reason,
    )
    return MeltingStepChangeResponse.from_domain(result_to_response(await uc(cmd, auth=auth)))


@router.patch("/melting-steps/{step_id}", response_model=MeltingStepChangeResponse)
async def review_melting_step(
    step_id: uuid.UUID, body: ReviewMeltingStepRequest, auth: AuthDep, uc: ReviewMeltingStepDep
) -> MeltingStepChangeResponse:
    """Accept, reject or correct a melting step, then recalculate the run."""
    cmd = ReviewMeltingStepCommand(
        workspace_id=auth.workspace_id,
        step_id=step_id,
        expected_version=body.expected_version,
        status=body.status,
        value=body.value,
        reason=body.reason,
    )
    return MeltingStepChangeResponse.from_domain(result_to_response(await uc(cmd, auth=auth)))
