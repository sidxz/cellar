"""Unit tests for FlagRunOutliers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.flag_run_outliers import (
    FlagRunOutliers,
    FlagRunOutliersCommand,
    OutlierFlagResult,
)
from cellar.application.screening.refit_curves_keeping_edits import CurveRefitOutcome
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.events import RunOutliersFlagged
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_import_instrument_file import FakeUoW
from tests.unit.domain.screening_assay.test_run import P, _instrument_run


class Harness:
    def __init__(self, status: RunStatus = RunStatus.DRAFT, locked: bool = False) -> None:
        self.run, (self.w1, self.w2, self.w3) = _instrument_run(status=status, locked=locked)
        self.ws = self.run.workspace_id
        self.auth = FakeAuth(workspace_id=self.ws)
        self.uow = FakeUoW([self.run])
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(return_value=self.run)
        self.readout_repo = AsyncMock()
        self.readout_repo.set_outlier = AsyncMock(side_effect=lambda ws, run, ids, **_: set(ids))
        # Rows before the flag, then after the recalculation.
        self.readout_repo.find_by_run = AsyncMock(side_effect=[["before"], ["after"]])
        self.protocol_repo = AsyncMock()
        self.protocol = object()
        self.protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=self.protocol)
        self.engine = AsyncMock()
        self.engine.compute_for_run = AsyncMock(return_value=Success(object()))
        self.curves = AsyncMock()
        self.curves.refit = AsyncMock(return_value=CurveRefitOutcome(refitted=1))
        self.dispatcher = AsyncMock()
        self.uc = FlagRunOutliers(
            uow=self.uow,
            run_repo=self.run_repo,
            readout_repo=self.readout_repo,
            protocol_repo=self.protocol_repo,
            calculation_engine=self.engine,
            curves=self.curves,
            dispatcher=self.dispatcher,
        )

    async def __call__(self, ids, outlier=True, reason=None, auth=None):  # type: ignore[no-untyped-def]
        cmd = FlagRunOutliersCommand(
            workspace_id=self.ws,
            run_id=self.run.id,
            well_ids=tuple(ids),
            outlier=outlier,
            reason=reason,
        )
        return await self.uc(cmd, auth=auth or self.auth)

    def assert_nothing_written(self) -> None:
        self.readout_repo.set_outlier.assert_not_awaited()
        assert self.uow.committed is False
        self.dispatcher.dispatch_all.assert_not_awaited()
        self.engine.compute_for_run.assert_not_awaited()
        self.curves.refit.assert_not_awaited()


async def test_flagging_sets_the_rows_audits_the_changed_positions_and_recalculates():
    h = Harness()
    # w1 was flagged already: only w3's rows change.
    h.readout_repo.set_outlier.side_effect = None
    h.readout_repo.set_outlier.return_value = {h.w3.id}

    out = (await h([h.w1.id, h.w3.id], reason="bubble")).unwrap()

    assert out == OutlierFlagResult(wells_changed=1, recalculated=True, compute_warning=None)
    h.readout_repo.set_outlier.assert_awaited_once_with(
        h.ws, h.run.id, [h.w1.id, h.w3.id], outlier=True
    )
    assert h.uow.committed
    (event,) = h.dispatcher.dispatch_all.await_args.args[0]
    assert isinstance(event, RunOutliersFlagged)
    assert ([p.label for p in event.positions], event.outlier) == ([f"Cassette 1 · {P(3)}"], True)
    assert event.reason == "bubble"
    # The run is saved (its version guards against an approval meanwhile), recalculated
    # without the full refit, and the curves the flag touched are refitted keeping edits.
    h.run_repo.save.assert_awaited_once_with(h.run)
    h.engine.compute_for_run.assert_awaited_once_with(
        h.run.id, workspace_id=h.ws, refit_curves=False
    )
    h.curves.refit.assert_awaited_once_with(
        run=h.run, protocol=h.protocol, before=["before"], after=["after"]
    )


async def test_removing_flags_passes_outlier_false():
    h = Harness(status=RunStatus.COMPLETED)
    out = (await h([h.w2.id], outlier=False, reason="was fine")).unwrap()
    assert out.wells_changed == 1
    h.readout_repo.set_outlier.assert_awaited_once_with(h.ws, h.run.id, [h.w2.id], outlier=False)


async def test_nothing_to_change_commits_nothing_and_does_not_recalculate():
    h = Harness()
    h.readout_repo.set_outlier.side_effect = None
    h.readout_repo.set_outlier.return_value = set()
    out = (await h([h.w1.id])).unwrap()
    assert out == OutlierFlagResult(wells_changed=0, recalculated=False, compute_warning=None)
    assert h.uow.committed is False
    h.engine.compute_for_run.assert_not_awaited()


async def test_a_failed_recalculation_saves_nothing_and_says_why():
    h = Harness()
    h.engine.compute_for_run.return_value = Failure(
        ValidationError("PERCENT_INHIBITION requires at least one low-signal control")
    )
    error = (await h([h.w1.id])).failure()
    assert isinstance(error, ValidationError)
    assert error.message.startswith("Not saved") and "low-signal control" in error.message
    assert h.uow.committed is False
    h.dispatcher.dispatch_all.assert_not_awaited()
    h.curves.refit.assert_not_awaited()


async def test_removed_curves_are_reported():
    h = Harness()
    h.curves.refit.return_value = CurveRefitOutcome(removed=2)
    out = (await h([h.w1.id])).unwrap()
    assert out.compute_warning is not None and "2 curves removed" in out.compute_warning


async def test_refused_on_a_locked_or_approved_run_before_any_write():
    for status, locked in ((RunStatus.APPROVED, False), (RunStatus.COMPLETED, True)):
        h = Harness(status=status, locked=locked)
        result = await h([h.w1.id])
        assert isinstance(result.failure(), ConflictError)
        h.assert_nothing_written()


async def test_a_well_not_on_the_run_is_refused():
    h = Harness()
    result = await h([uuid.uuid4()])
    assert isinstance(result.failure(), ValidationError)
    h.assert_nothing_written()


async def test_unknown_run_is_not_found():
    h = Harness()
    h.run_repo.find_by_id_in_workspace.return_value = None
    result = await h([h.w1.id])
    assert isinstance(result.failure(), NotFoundError)
    h.assert_nothing_written()


async def test_viewers_and_other_workspaces_are_refused():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h([h.w1.id], auth=FakeAuth(workspace_id=h.ws, role="viewer"))
    # Another workspace's run is not found, so its existence does not leak.
    with pytest.raises(NotFoundError):
        await h([h.w1.id], auth=FakeAuth(workspace_id=uuid.uuid4()))
    h.assert_nothing_written()
