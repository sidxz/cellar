"""Unit tests for AddMeltingStep and ReviewMeltingStep."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.manage_melting_steps import (
    AddMeltingStep,
    AddMeltingStepCommand,
    MeltingStepChange,
    ReviewMeltingStep,
    ReviewMeltingStepCommand,
)
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.melting_step import (
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_import_instrument_file import FakeUoW
from tests.unit.domain.screening_assay.test_run import _instrument_run

X_RANGE = (25.0, 95.0)


class Harness:
    def __init__(self, status: RunStatus = RunStatus.DRAFT, locked: bool = False) -> None:
        self.run, (self.w1, self.w2, _) = _instrument_run(status=status, locked=locked)
        self.ws = self.run.workspace_id
        self.auth = FakeAuth(workspace_id=self.ws)
        self.step = MeltingStep(
            workspace_id=self.ws,
            run_id=self.run.id,
            well_id=self.w2.id,
            channel_key="ratio",
            source=MeltingStepSource.INSTRUMENT,
            value=55.0,
            instrument_value=55.0,
            instrument_label="T1",
        )
        self.uow = FakeUoW([])
        self.uow.session = object()
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(return_value=self.run)
        self.curve_repo = AsyncMock()
        self.curve_repo.find_by_wells = AsyncMock(
            return_value=[SimpleNamespace(well_id=self.w2.id, x=X_RANGE)]
        )
        self.step_repo = AsyncMock()
        self.step_repo.find_by_id = AsyncMock(return_value=self.step)
        self.audit = AsyncMock()
        self.engine = AsyncMock()
        self.engine.compute_for_run = AsyncMock(return_value=Success(SimpleNamespace()))
        deps = dict(
            uow=self.uow,
            run_repo=self.run_repo,
            curve_repo=self.curve_repo,
            step_repo=self.step_repo,
            audit=self.audit,
            calculation_engine=self.engine,
        )
        self.add = AddMeltingStep(**deps)
        self.review = ReviewMeltingStep(**deps)

    def add_cmd(self, **kw):  # type: ignore[no-untyped-def]
        base = dict(
            workspace_id=self.ws, run_id=self.run.id, well_id=self.w2.id,
            channel_key="ratio", value=60.0,
        )  # fmt: skip
        return AddMeltingStepCommand(**{**base, **kw})

    def review_cmd(self, **kw):  # type: ignore[no-untyped-def]
        base = dict(
            workspace_id=self.ws, step_id=self.step.id, expected_version=1,
            status=MeltingStepStatus.ACCEPTED, value=55.0,
        )  # fmt: skip
        return ReviewMeltingStepCommand(**{**base, **kw})

    async def do_add(self, auth=None, **kw):  # type: ignore[no-untyped-def]
        return await self.add(self.add_cmd(**kw), auth=auth or self.auth)

    async def do_review(self, auth=None, **kw):  # type: ignore[no-untyped-def]
        return await self.review(self.review_cmd(**kw), auth=auth or self.auth)

    def assert_nothing_written(self) -> None:
        self.step_repo.add.assert_not_awaited()
        self.step_repo.update.assert_not_awaited()
        self.audit.record.assert_not_awaited()
        assert self.uow.committed is False
        self.engine.compute_for_run.assert_not_awaited()


async def test_add_manual_step_saves_audits_and_recalculates():
    h = Harness()
    out = (await h.do_add(reason="  visible shoulder ")).unwrap()
    assert isinstance(out, MeltingStepChange) and out.recalculated and out.compute_warning is None
    step = out.step
    assert step.source is MeltingStepSource.MANUAL and step.value == 60.0
    assert step.reason == "visible shoulder"
    h.step_repo.add.assert_awaited_once_with(step)
    kw = h.audit.record.await_args.kwargs
    assert kw["operation_type"] is OperationType.DATA_ENTRY
    assert kw["entity_type"] == "MeltingStep" and kw["entity_id"] == step.id
    assert kw["user_id"] == h.auth.user_id and kw["session"] is h.uow.session
    assert kw["reason"] == "visible shoulder"
    assert {(e.field_name, e.action, e.new_value) for e in kw["entries"]} == {
        ("value", AuditAction.CREATE, "60"),
        ("status", AuditAction.CREATE, "unreviewed"),
    }
    assert h.uow.committed
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)


async def test_reject_recalculates_run():
    h = Harness()
    out = (await h.do_review(status=MeltingStepStatus.REJECTED, reason="noise")).unwrap()
    assert out.recalculated and out.step.status is MeltingStepStatus.REJECTED
    h.step_repo.update.assert_awaited_once_with(h.step, expected_version=1)
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)
    assert h.audit.record.await_args.kwargs["operation_type"] is OperationType.PROPERTY_EDIT


async def test_correct_value_writes_audit_with_old_and_new_and_reason():
    h = Harness()
    (await h.do_review(value=57.5, reason="manual read")).unwrap()
    kw = h.audit.record.await_args.kwargs
    assert kw["reason"] == "manual read" and kw["entity_type"] == "MeltingStep"
    by_field = {e.field_name: e for e in kw["entries"]}
    assert (by_field["value"].old_value, by_field["value"].new_value) == ("55", "57.5")
    assert by_field["value"].action is AuditAction.UPDATE
    assert by_field["status"].new_value == "accepted"


async def test_review_without_changes_writes_nothing():
    h = Harness()
    out = (await h.do_review(status=MeltingStepStatus.UNREVIEWED)).unwrap()
    assert out == MeltingStepChange(h.step, False)
    h.assert_nothing_written()


async def test_stale_version_is_conflict():
    h = Harness()
    h.step_repo.update.side_effect = ConflictError("changed by someone else")
    failure = (await h.do_review(expected_version=1)).failure()
    assert isinstance(failure, ConflictError)
    h.audit.record.assert_not_awaited()
    assert h.uow.committed is False
    h.engine.compute_for_run.assert_not_awaited()


@pytest.mark.parametrize("which", ["add", "review"])
async def test_completed_run_refuses_step_changes(which):
    h = Harness(status=RunStatus.COMPLETED)
    out = await (h.do_add() if which == "add" else h.do_review())
    failure = out.failure()
    assert isinstance(failure, ConflictError)
    assert (
        str(failure) == "Melting steps can be changed only while the run is draft or in progress"
    )
    h.assert_nothing_written()


@pytest.mark.parametrize("which", ["add", "review"])
async def test_locked_run_refuses_step_changes(which):
    h = Harness(locked=True)
    out = await (h.do_add() if which == "add" else h.do_review())
    failure = out.failure()
    assert isinstance(failure, ConflictError) and str(failure) == "This run is locked"
    h.assert_nothing_written()


@pytest.mark.parametrize("which", ["add", "review"])
async def test_value_outside_trace_range_is_validation_error(which):
    h = Harness()
    out = await (h.do_add(value=99.0) if which == "add" else h.do_review(value=99.0, reason="x"))
    assert isinstance(out.failure(), ValidationError)
    h.assert_nothing_written()


async def test_trace_range_is_min_to_max_inclusive():
    h = Harness()
    assert isinstance(await h.do_add(value=95.0), Success)


@pytest.mark.parametrize("which", ["add", "review"])
async def test_position_without_trace_on_channel_is_validation_error(which):
    h = Harness()
    h.curve_repo.find_by_wells.return_value = []
    out = await (h.do_add() if which == "add" else h.do_review())
    failure = out.failure()
    assert isinstance(failure, ValidationError)
    assert str(failure) == "This position has no trace for that signal"
    h.assert_nothing_written()


async def test_reject_without_reason_is_validation_error():
    h = Harness()
    failure = (await h.do_review(status=MeltingStepStatus.REJECTED)).failure()
    assert isinstance(failure, ValidationError)
    h.assert_nothing_written()


async def test_engine_failure_becomes_compute_warning():
    h = Harness()
    h.engine.compute_for_run.return_value = Failure(ValidationError("boom"))
    out = (await h.do_review(status=MeltingStepStatus.REJECTED, reason="noise")).unwrap()
    assert out.recalculated is False and out.compute_warning
    assert h.uow.committed


async def test_step_or_run_not_found():
    h = Harness()
    h.run_repo.find_by_id_in_workspace.return_value = None
    assert isinstance((await h.do_add()).failure(), NotFoundError)
    assert isinstance((await h.do_review()).failure(), NotFoundError)
    h.step_repo.find_by_id.return_value = None
    h.run_repo.find_by_id_in_workspace.return_value = h.run
    failure = (await h.do_review()).failure()
    assert isinstance(failure, NotFoundError)
    h.step_repo.find_by_id.assert_awaited_with(h.ws, h.step.id)
    h.assert_nothing_written()


async def test_viewer_raises_authorization_error():
    h = Harness()
    viewer = FakeAuth(role="viewer", workspace_id=h.ws)
    with pytest.raises(AuthorizationError):
        await h.do_add(auth=viewer)
    with pytest.raises(AuthorizationError):
        await h.do_review(auth=viewer)
    h.assert_nothing_written()


async def test_other_workspace_is_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h.do_add(auth=FakeAuth())
    with pytest.raises(NotFoundError):
        await h.do_review(auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()
    h.step_repo.find_by_id.assert_not_awaited()
