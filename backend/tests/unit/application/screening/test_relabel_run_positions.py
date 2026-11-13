"""Unit tests for RelabelRunPositions."""

from __future__ import annotations

import uuid
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.relabel_run_positions import (
    RelabelResult,
    RelabelRunPositions,
    RelabelRunPositionsCommand,
)
from cellar.domain.screening_assay.enums import HolderKind, RunStatus, WellType
from cellar.domain.screening_assay.events import RunPositionsRelabelled
from cellar.domain.screening_assay.holder import position_label
from cellar.domain.screening_assay.run import PositionEdit, Well
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_import_instrument_file import FakeUoW
from tests.unit.domain.screening_assay.test_run import _instrument_run


def E(w: Well, **new) -> PositionEdit:
    return PositionEdit(w.id, w.values, replace(w.values, **new))


def P(n: int) -> str:
    return position_label(HolderKind.CASSETTE, "A", n)


class Harness:
    def __init__(self, status: RunStatus = RunStatus.DRAFT, locked: bool = False) -> None:
        self.run, (self.w1, self.w2, self.w3) = _instrument_run(status=status, locked=locked)
        self.auth = FakeAuth(workspace_id=self.run.workspace_id)
        self.ws = self.run.workspace_id
        self.batch1 = SimpleNamespace(
            id=self.w2.batch_id,
            molecule_id=uuid.uuid4(),
            batch_number=SimpleNamespace(value="B-1"),
        )
        self.batch2 = SimpleNamespace(
            id=uuid.uuid4(), molecule_id=uuid.uuid4(), batch_number=SimpleNamespace(value="B-2")
        )
        known = {b.id: b for b in (self.batch1, self.batch2)}
        self.readout_on_w2 = SimpleNamespace(id=uuid.uuid4(), well_id=self.w2.id)
        self.readout_on_w3 = SimpleNamespace(id=uuid.uuid4(), well_id=self.w3.id)

        self.uow = FakeUoW([self.run])
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(return_value=self.run)
        self.readout_repo = AsyncMock()
        self.readout_repo.find_by_run = AsyncMock(
            return_value=[self.readout_on_w2, self.readout_on_w3]
        )
        self.readout_repo.repoint_well = AsyncMock(return_value=0)
        self.curve_repo = AsyncMock()
        self.curve_repo.list_channels = AsyncMock(return_value=[SimpleNamespace(key="ratio")])
        self.batch_repo = AsyncMock()
        self.batch_repo.find_by_ids = AsyncMock(
            side_effect=lambda ws, ids: [known[i] for i in ids if i in known]
        )
        self.campaign_repo = AsyncMock()
        self.campaign_repo.find_names_using_readouts = AsyncMock(return_value={})
        self.engine = AsyncMock()
        self.engine.compute_for_run = AsyncMock(return_value=Success(SimpleNamespace()))
        self.dispatcher = AsyncMock()
        self.uc = RelabelRunPositions(
            uow=self.uow,
            run_repo=self.run_repo,
            readout_repo=self.readout_repo,
            curve_repo=self.curve_repo,
            batch_repo=self.batch_repo,
            campaign_repo=self.campaign_repo,
            calculation_engine=self.engine,
            dispatcher=self.dispatcher,
        )

    def cmd(self, edits: list[PositionEdit], reason: str | None = None):  # type: ignore[no-untyped-def]
        return RelabelRunPositionsCommand(
            workspace_id=self.ws, run_id=self.run.id, edits=tuple(edits), reason=reason
        )

    async def __call__(self, edits: list[PositionEdit], reason: str | None = None, auth=None):  # type: ignore[no-untyped-def]
        return await self.uc(self.cmd(edits, reason), auth=auth or self.auth)

    def assert_nothing_written(self) -> None:
        self.run_repo.save.assert_not_awaited()
        self.readout_repo.repoint_well.assert_not_awaited()
        assert self.uow.committed is False
        self.dispatcher.dispatch_all.assert_not_awaited()
        self.engine.compute_for_run.assert_not_awaited()


async def test_label_and_note_change_saves_once_and_does_not_recalculate():
    h = Harness()
    out = (await h([E(h.w2, label="y")])).unwrap()
    assert out == RelabelResult(positions_changed=1, readouts_repointed=0, recalculated=False)
    h.run_repo.save.assert_awaited_once_with(h.run)
    h.readout_repo.repoint_well.assert_not_awaited()
    h.engine.compute_for_run.assert_not_awaited()
    h.campaign_repo.find_names_using_readouts.assert_not_awaited()
    assert h.uow.committed
    (event,) = h.dispatcher.dispatch_all.await_args.args[0]
    assert isinstance(event, RunPositionsRelabelled)


async def test_batch_change_repoints_readouts_and_recalculates():
    h = Harness()
    h.readout_repo.repoint_well.return_value = 2
    out = (await h([E(h.w2, batch_id=h.batch2.id)])).unwrap()
    h.readout_repo.repoint_well.assert_awaited_once_with(
        h.ws, h.run.id, h.w2.id, batch_id=h.batch2.id, molecule_id=h.batch2.molecule_id
    )
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)
    assert (out.readouts_repointed, out.recalculated, out.compute_warning) == (2, True, None)
    h.campaign_repo.find_names_using_readouts.assert_awaited_once_with(h.ws, [h.readout_on_w2.id])
    (event,) = h.dispatcher.dispatch_all.await_args.args[0]
    assert event.positions[0].fields[0].old == "B-1" and event.positions[0].fields[0].new == "B-2"


async def test_batch_cleared_repoints_to_no_compound():
    h = Harness()
    h.readout_repo.repoint_well.return_value = 1
    out = (await h([E(h.w2, batch_id=None)])).unwrap()
    h.readout_repo.repoint_well.assert_awaited_once_with(
        h.ws, h.run.id, h.w2.id, batch_id=None, molecule_id=None
    )
    assert (out.readouts_repointed, out.recalculated) == (1, True)


@pytest.mark.parametrize("new", [{"well_type": WellType.BLANK}, {"dose": 25.0}])
async def test_role_or_concentration_change_recalculates_without_repointing(new):
    h = Harness()
    out = (await h([E(h.w2, **new)])).unwrap()
    h.readout_repo.repoint_well.assert_not_awaited()
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)
    assert (out.positions_changed, out.readouts_repointed, out.recalculated) == (1, 0, True)


async def test_no_changes_saves_nothing_and_dispatches_nothing():
    h = Harness()
    out = (await h([E(h.w2), E(h.w3, label="  ")])).unwrap()
    assert out == RelabelResult(0, 0, False)
    h.assert_nothing_written()


async def test_stale_expected_is_conflict_and_nothing_written():
    h = Harness()
    stale = PositionEdit(
        h.w2.id, replace(h.w2.values, label="old"), replace(h.w2.values, label="mine")
    )
    failure = (await h([E(h.w3, note="n"), stale])).failure()
    assert isinstance(failure, ConflictError) and P(2) in str(failure)
    h.assert_nothing_written()
    assert (h.w2.label, h.w3.note) == ("x", None)


@pytest.mark.parametrize("new", [{"well_type": WellType.BLANK}, {"dose": 1.0}, {"batch_id": None}])
async def test_completed_run_refuses_role_batch_concentration(new):
    h = Harness(status=RunStatus.COMPLETED)
    result = await h([E(h.w2, **new)], reason="typo")
    assert isinstance(result, Failure) and isinstance(result.failure(), ConflictError)
    h.assert_nothing_written()


async def test_completed_run_label_edit_needs_a_reason_and_the_event_carries_it():
    h = Harness(status=RunStatus.COMPLETED)
    failure = (await h([E(h.w2, label="y")])).failure()
    assert isinstance(failure, ValidationError)
    h.assert_nothing_written()

    assert isinstance(await h([E(h.w2, label="y")], reason=" typo "), Success)
    (event,) = h.dispatcher.dispatch_all.await_args.args[0]
    assert event.reason == "typo"


async def test_locked_run_is_conflict():
    h = Harness(status=RunStatus.COMPLETED, locked=True)
    failure = (await h([E(h.w2, label="y")], reason="typo")).failure()
    assert isinstance(failure, ConflictError)
    h.assert_nothing_written()


async def test_run_without_measured_curves_is_conflict():
    h = Harness()
    h.curve_repo.list_channels.return_value = []
    failure = (await h([E(h.w2, label="y")])).failure()
    assert isinstance(failure, ConflictError) and "no measured curves" in str(failure)
    h.curve_repo.list_channels.assert_awaited_once_with(h.ws, h.run.id)
    h.assert_nothing_written()


async def test_batch_not_in_workspace_is_not_found_and_nothing_written():
    h = Harness()
    stranger = uuid.uuid4()
    failure = (await h([E(h.w3, batch_id=stranger)])).failure()
    assert isinstance(failure, NotFoundError) and str(stranger) in str(failure)
    ids = h.batch_repo.find_by_ids.await_args.args
    assert ids[0] == h.ws and set(ids[1]) == {stranger}
    h.assert_nothing_written()
    assert h.w3.batch_id is None


async def test_batch_change_refused_when_a_campaign_uses_the_readouts():
    h = Harness()
    h.campaign_repo.find_names_using_readouts.return_value = {h.readout_on_w2.id: "Campaign A"}
    failure = (await h([E(h.w2, batch_id=h.batch2.id)])).failure()
    assert isinstance(failure, ConflictError) and "Campaign A" in str(failure)
    assert P(2) in str(failure)
    h.readout_repo.find_by_run.assert_awaited_once_with(h.ws, h.run.id)
    h.assert_nothing_written()


async def test_label_change_on_a_position_a_campaign_uses_is_allowed():
    h = Harness()
    h.campaign_repo.find_names_using_readouts.return_value = {h.readout_on_w2.id: "Campaign A"}
    assert isinstance(await h([E(h.w2, label="y", dose=12.0)]), Success)
    h.campaign_repo.find_names_using_readouts.assert_not_awaited()
    h.readout_repo.find_by_run.assert_not_awaited()


async def test_engine_failure_becomes_compute_warning():
    h = Harness()
    h.engine.compute_for_run.return_value = Failure(ValidationError("engine broke"))
    out = (await h([E(h.w2, dose=25.0)])).unwrap()
    assert out.compute_warning == "engine broke" and out.recalculated is False
    assert h.uow.committed


async def test_run_not_found():
    h = Harness()
    h.run_repo.find_by_id_in_workspace.return_value = None
    failure = (await h([E(h.w2, label="y")])).failure()
    assert isinstance(failure, NotFoundError)
    h.run_repo.find_by_id_in_workspace.assert_awaited_once_with(h.ws, h.run.id)
    h.assert_nothing_written()


async def test_viewer_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h([E(h.w2, label="y")], auth=FakeAuth(role="viewer", workspace_id=h.ws))
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h([E(h.w2, label="y")], auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()
