"""GetMeltingAnalysis: a run's melting steps, window results and step-count checks."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.get_melting_analysis import (
    GetMeltingAnalysis,
    GetMeltingAnalysisQuery,
)
from cellar.application.screening.manage_melting_steps import NOT_EDITABLE
from cellar.domain.screening_assay.enums import (
    PlateFormat,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    RunStatus,
    WellType,
)
from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig, WindowFlag
from cellar.domain.screening_assay.melting_step import (
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.errors import AuthorizationError, NotFoundError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_import_instrument_file import FakeUoW

WS = uuid.uuid4()
USER = uuid.uuid4()
CH = "350nm"
WINDOWS = {"Low": (25.0, 50.0), "Main": (50.0, 85.0)}


def _rd(window: str, measure: MeltMeasure) -> ReadoutDefinition:
    low, high = WINDOWS[window]
    prefix = "Tm" if measure is MeltMeasure.TM else "ΔTm"
    return ReadoutDefinition(
        protocol_id=uuid.UUID(int=0),
        name=f"{prefix} ({window})",
        data_type=ReadoutDataType.NUMERIC,
        unit="°C",
        aggregation=ReadoutAggregation.MEAN,
        melt_config=MeltReadoutConfig(
            window=window, measure=measure, channel_key=CH, low=low, high=high
        ),
    )


class Harness:
    def __init__(self, status: RunStatus = RunStatus.DRAFT, locked: bool = False) -> None:
        # Declared high window first: results must still come back ordered by low.
        self.defs = [_rd(w, m) for w in ("Main", "Low") for m in MeltMeasure]
        self.protocol = Protocol.create(
            workspace_id=WS,
            name="Thermal shift",
            protocol_type=ProtocolType.BIOCHEMICAL,
            created_by=USER,
            readout_definitions=self.defs,
        )
        self.run = Run.create(
            workspace_id=WS,
            protocol_id=self.protocol.id,
            run_date=date(2026, 11, 13),
            operator=USER,
        )
        plate = Plate(run_id=self.run.id, plate_number=1, format=PlateFormat.F96)
        self.run.plates.append(plate)
        self.ref = Well(plate_id=plate.id, row="A", column=1, well_type=WellType.REFERENCE)
        self.sample = Well(plate_id=plate.id, row="A", column=2, well_type=WellType.SAMPLE)
        self.run.wells.extend([self.ref, self.sample])
        self.run.status = status
        self.run.is_locked = locked
        self.steps: list[MeltingStep] = []
        self.auth = FakeAuth(role="viewer", workspace_id=WS)
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(return_value=self.run)
        self.protocol_repo = AsyncMock()
        self.protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=self.protocol)
        self.step_repo = AsyncMock()
        self.step_repo.find_by_run = AsyncMock(side_effect=lambda ws, rid: list(self.steps))
        self.traced = {(self.ref.id, CH), (self.sample.id, CH)}
        self.curve_repo = AsyncMock()
        self.curve_repo.list_traced = AsyncMock(side_effect=lambda ws, rid: set(self.traced))
        self.uc = GetMeltingAnalysis(
            uow=FakeUoW([]),
            run_repo=self.run_repo,
            protocol_repo=self.protocol_repo,
            step_repo=self.step_repo,
            curve_repo=self.curve_repo,
        )

    def step(self, well: Well, value: float, status=MeltingStepStatus.UNREVIEWED) -> MeltingStep:
        s = MeltingStep(
            workspace_id=WS,
            run_id=self.run.id,
            well_id=well.id,
            channel_key=CH,
            source=MeltingStepSource.MANUAL,
            value=value,
            status=status,
        )
        self.steps.append(s)
        return s

    async def read(self, auth=None, run_id=None):  # type: ignore[no-untyped-def]
        return await self.uc(
            GetMeltingAnalysisQuery(workspace_id=WS, run_id=run_id or self.run.id),
            auth=auth or self.auth,
        )


async def test_returns_steps_windows_and_step_checks():
    h = Harness()
    h.step(h.sample, 70.0)
    h.step(h.ref, 71.0)
    h.step(h.ref, 36.0)
    out = (await h.read()).unwrap()

    assert out.run_id == h.run.id
    assert out.edit_refusal is None
    assert [(s.well_id, s.value) for s in out.steps] == [
        (h.ref.id, 36.0),
        (h.ref.id, 71.0),
        (h.sample.id, 70.0),
    ]
    assert [w.window for w in out.windows] == ["Low", "Main"]
    low, main = out.windows
    assert (low.channel_key, low.low, low.high) == (CH, 25.0, 50.0)
    by_name = {d.name: d.id for d in h.defs}
    assert main.tm_readout_id == by_name["Tm (Main)"]
    assert main.delta_tm_readout_id == by_name["ΔTm (Main)"]
    assert main.result.reference_tm == 71.0
    sample_main = next(p for p in main.result.positions if p.well_id == h.sample.id)
    assert (sample_main.tm, sample_main.delta_tm) == (70.0, -1.0)
    sample_low = next(p for p in low.result.positions if p.well_id == h.sample.id)
    assert sample_low.flags == (WindowFlag.NO_STEP,)
    assert [c.channel_key for c in out.step_checks] == [CH]
    assert out.step_checks[0].check.differs == frozenset({h.sample.id})


async def test_rejected_steps_are_listed_but_do_not_count():
    h = Harness()
    h.step(h.ref, 71.0)
    rejected = h.step(h.sample, 70.0, MeltingStepStatus.REJECTED)
    out = (await h.read()).unwrap()

    assert rejected in out.steps
    main = out.windows[1]
    sample = next(p for p in main.result.positions if p.well_id == h.sample.id)
    assert sample.tm is None
    assert sample.flags == (WindowFlag.NO_STEP,)


@pytest.mark.parametrize(
    ("status", "locked", "expected"),
    [
        (RunStatus.DRAFT, False, None),
        (RunStatus.IN_PROGRESS, False, None),
        (RunStatus.COMPLETED, False, NOT_EDITABLE),
        (RunStatus.DRAFT, True, "This run is locked"),
        (RunStatus.COMPLETED, True, "This run is locked"),
    ],
)
async def test_edit_refusal_on_completed_and_locked_runs(status, locked, expected):
    h = Harness(status=status, locked=locked)
    assert (await h.read()).unwrap().edit_refusal == expected


async def test_run_not_found():
    h = Harness()
    h.run_repo.find_by_id_in_workspace = AsyncMock(return_value=None)
    failure = (await h.read()).failure()
    assert isinstance(failure, NotFoundError)
    h.run_repo.find_by_id_in_workspace.assert_awaited_with(WS, h.run.id)
    h.step_repo.find_by_run.assert_not_awaited()


async def test_unauthenticated_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h.read(auth=FakeAuth(role="guest", workspace_id=WS))
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_other_workspace_is_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h.read(auth=FakeAuth(role="viewer"))
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_position_without_a_trace_on_the_channel_is_not_evaluated():
    h = Harness()
    h.step(h.ref, 71.0)
    h.traced = {(h.ref.id, CH), (h.sample.id, "other")}
    out = (await h.read()).unwrap()

    for w in out.windows:
        assert [p.well_id for p in w.result.positions] == [h.ref.id]
    (check,) = out.step_checks
    assert check.check.differs == frozenset()
