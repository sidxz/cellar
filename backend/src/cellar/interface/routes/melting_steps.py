"""A run's melting analysis, adding, reviewing and assigning its melting steps, and the
candidate peaks of a position."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from cellar.application.screening.get_melting_analysis import (
    ChannelStepCheck,
    GetMeltingAnalysisQuery,
    MeltingAnalysis,
    WindowAnalysis,
    WindowSeries,
)
from cellar.application.screening.get_peak_candidates import (
    GetPeakCandidatesQuery,
    SignalPeakCandidates,
)
from cellar.application.screening.manage_melting_steps import (
    AddMeltingStepCommand,
    AssignMeltingStepCommand,
    MeltingStepChange,
    ReviewMeltingStepCommand,
)
from cellar.domain.screening_assay.melt_window import (
    MeltMeasure,
    NamedBy,
    PositionWindowResult,
)
from cellar.domain.screening_assay.melting_step import (
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.domain.screening_assay.peak_detection import PeakCandidate, PeakDirection
from cellar.interface.dependencies import (
    AddMeltingStepDep,
    AssignMeltingStepDep,
    AuthDep,
    GetMeltingAnalysisDep,
    GetPeakCandidatesDep,
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
    # The temperature window this step was assigned to by hand; null when it is named by range.
    assigned_window: str | None
    assignment_reason: str | None
    assigned_by: uuid.UUID | None
    assigned_at: datetime | None
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
            assigned_window=s.assigned_window,
            assignment_reason=s.assignment_reason,
            assigned_by=s.assigned_by,
            assigned_at=s.assigned_at,
            version=s.version,
        )


class MeltWindowPositionModel(BaseModel):
    well_id: uuid.UUID
    tm: float | None
    delta_tm: float | None
    flags: list[str]
    # How the Tm was named and the step that supplied it; both null when there is no Tm.
    named_by: NamedBy | None
    step_id: uuid.UUID | None

    @classmethod
    def from_domain(cls, p: PositionWindowResult) -> MeltWindowPositionModel:
        return cls(
            well_id=p.well_id,
            tm=p.tm,
            delta_tm=p.delta_tm,
            flags=[f.value for f in p.flags],
            named_by=p.named_by,
            step_id=p.step_id,
        )


class MeltSeriesValueModel(BaseModel):
    batch_id: uuid.UUID
    value: float
    # "=" or ">" (a lowest shifting concentration not reached: above the highest tested).
    qualifier: str
    # Where the value belongs: where Max ΔTm occurred, the lowest shifting
    # concentration itself, or the stated concentration. Protocol dose unit.
    concentration: float | None


class MeltSeriesModel(BaseModel):
    """A descriptive series readout of the window and its value per batch (no fit)."""

    readout_id: uuid.UUID
    readout_name: str
    measure: MeltMeasure
    threshold: float | None
    concentration: float | None
    values: list[MeltSeriesValueModel]

    @classmethod
    def from_domain(cls, s: WindowSeries) -> MeltSeriesModel:
        return cls(
            readout_id=s.readout_id,
            readout_name=s.readout_name,
            measure=s.measure,
            threshold=s.threshold,
            concentration=s.concentration,
            values=[
                MeltSeriesValueModel(
                    batch_id=v.batch_id,
                    value=v.value,
                    qualifier=v.qualifier.value,
                    concentration=v.concentration,
                )
                for v in s.values
            ],
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
    series: list[MeltSeriesModel]

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
            series=[MeltSeriesModel.from_domain(x) for x in w.series],
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
    # Ids of counted steps that are assigned to no window and lie inside none on their signal.
    outside_every_window: list[uuid.UUID]

    @classmethod
    def from_domain(cls, a: MeltingAnalysis) -> MeltingAnalysisResponse:
        return cls(
            run_id=a.run_id,
            edit_refusal=a.edit_refusal,
            steps=[MeltingStepModel.from_domain(s) for s in a.steps],
            windows=[MeltWindowModel.from_domain(w) for w in a.windows],
            step_checks=[StepCheckModel.from_domain(c) for c in a.step_checks],
            outside_every_window=list(a.outside_every_window),
        )


class AddMeltingStepRequest(BaseModel):
    well_id: uuid.UUID
    channel_key: str = Field(min_length=1)
    value: float = Field(allow_inf_nan=False)
    reason: str | None = Field(None, max_length=500)
    # Assign the new step to this window in the same save; the reason then serves both.
    assigned_window: str | None = Field(None, max_length=60)


class ReviewMeltingStepRequest(BaseModel):
    # The version the user read; a save over someone else's change is refused.
    expected_version: int = Field(ge=1)
    status: MeltingStepStatus
    value: float = Field(allow_inf_nan=False)
    reason: str | None = Field(None, max_length=500)


class AssignMeltingStepRequest(BaseModel):
    # The version the user read; a save over someone else's change is refused.
    expected_version: int = Field(ge=1)
    # A window of the run's protocol on the step's signal; null clears the assignment.
    window: str | None = Field(max_length=60)
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


class PeakCandidateModel(BaseModel):
    value: float
    direction: PeakDirection
    # How far it stands out, in units of the trace's own noise.
    strength: float

    @classmethod
    def from_domain(cls, c: PeakCandidate) -> PeakCandidateModel:
        return cls(value=c.value, direction=c.direction, strength=c.strength)


class SignalPeakCandidatesModel(BaseModel):
    channel_key: str
    # The smoothing the candidates were found with, in x units.
    smoothing_window: float
    # Strongest first.
    candidates: list[PeakCandidateModel]

    @classmethod
    def from_domain(cls, s: SignalPeakCandidates) -> SignalPeakCandidatesModel:
        return cls(
            channel_key=s.channel_key,
            smoothing_window=s.smoothing_window,
            candidates=[PeakCandidateModel.from_domain(c) for c in s.candidates],
        )


class PeakCandidatesResponse(BaseModel):
    # One entry per signal the position has a trace on, in the run's signal order.
    signals: list[SignalPeakCandidatesModel]


@router.get("/runs/{run_id}/melting-analysis", response_model=MeltingAnalysisResponse)
async def get_melting_analysis(
    run_id: uuid.UUID, auth: AuthDep, uc: GetMeltingAnalysisDep
) -> MeltingAnalysisResponse:
    """The run's melting steps, its temperature windows' Tm and ΔTm, and step-count checks."""
    result = await uc(
        GetMeltingAnalysisQuery(workspace_id=auth.workspace_id, run_id=run_id), auth=auth
    )
    return MeltingAnalysisResponse.from_domain(result_to_response(result))


@router.get(
    "/runs/{run_id}/wells/{well_id}/peak-candidates", response_model=PeakCandidatesResponse
)
async def get_peak_candidates(
    run_id: uuid.UUID,
    well_id: uuid.UUID,
    auth: AuthDep,
    uc: GetPeakCandidatesDep,
    smoothing_window: float | None = Query(None, gt=0, allow_inf_nan=False),
) -> PeakCandidatesResponse:
    """The candidate peaks of one position on each signal it has a trace on: the extrema of
    the smoothed first derivative that stand out from its noise, calculated on request and
    never stored. ``smoothing_window`` is in x units; its default and its upper bound are
    those of the derivative view of ``GET /runs/{run_id}/curves`` on the same signal."""
    result = await uc(
        GetPeakCandidatesQuery(
            workspace_id=auth.workspace_id,
            run_id=run_id,
            well_id=well_id,
            smoothing_window=smoothing_window,
        ),
        auth=auth,
    )
    signals = result_to_response(result)
    return PeakCandidatesResponse(
        signals=[SignalPeakCandidatesModel.from_domain(s) for s in signals]
    )


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
        assigned_window=body.assigned_window,
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


@router.put("/melting-steps/{step_id}/assignment", response_model=MeltingStepChangeResponse)
async def assign_melting_step(
    step_id: uuid.UUID, body: AssignMeltingStepRequest, auth: AuthDep, uc: AssignMeltingStepDep
) -> MeltingStepChangeResponse:
    """Assign a melting step to a temperature window, or clear the assignment, then recalculate."""
    cmd = AssignMeltingStepCommand(
        workspace_id=auth.workspace_id,
        step_id=step_id,
        expected_version=body.expected_version,
        window=body.window,
        reason=body.reason,
    )
    return MeltingStepChangeResponse.from_domain(result_to_response(await uc(cmd, auth=auth)))
