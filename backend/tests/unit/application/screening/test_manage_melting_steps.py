"""Unit tests for AddMeltingStep, ReviewMeltingStep, AssignMeltingStep and
AcceptMeltingSteps."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.manage_melting_steps import (
    PEAKS_COMPUTE_FAILED,
    AcceptMeltingSteps,
    AcceptMeltingStepsCommand,
    AddMeltingStep,
    AddMeltingStepCommand,
    AssignMeltingStep,
    AssignMeltingStepCommand,
    MeltingStepChange,
    MeltingStepsAccepted,
    ReviewMeltingStep,
    ReviewMeltingStepCommand,
)
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig
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
NOT_EDITABLE = "Peaks cannot be changed on an approved run"


def _window(name: str, channel: str = "ratio") -> SimpleNamespace:
    config = MeltReadoutConfig(
        window=name, measure=MeltMeasure.TM, channel_key=channel, low=25.0, high=85.0
    )
    return SimpleNamespace(melt_config=config)


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
        # Low and Main are windows on the step's signal; Other belongs to another signal.
        self.protocol_repo = AsyncMock()
        self.protocol_repo.find_by_id_in_workspace = AsyncMock(
            return_value=SimpleNamespace(
                readout_definitions=[
                    _window("Low"),
                    _window("Main"),
                    _window("Other", "350nm"),
                    SimpleNamespace(melt_config=None),
                ]
            )
        )
        self.steps = [self.step]
        self.step_repo = AsyncMock()
        self.step_repo.find_by_id = AsyncMock(return_value=self.step)
        self.step_repo.find_by_run = AsyncMock(side_effect=lambda ws, run_id: list(self.steps))
        self.audit = AsyncMock()
        self.engine = AsyncMock()
        self.engine.compute_for_run = AsyncMock(return_value=Success(SimpleNamespace()))
        deps = dict(
            uow=self.uow,
            run_repo=self.run_repo,
            protocol_repo=self.protocol_repo,
            curve_repo=self.curve_repo,
            step_repo=self.step_repo,
            audit=self.audit,
            calculation_engine=self.engine,
        )
        self.add = AddMeltingStep(**deps)
        self.review = ReviewMeltingStep(**deps)
        self.assign = AssignMeltingStep(**deps)
        self.accept = AcceptMeltingSteps(**deps)

    def peak(self, well=None, *, window=None, version=1):  # type: ignore[no-untyped-def]
        """Another peak of the run on the same signal, on the step's position by default."""
        peak = MeltingStep(
            workspace_id=self.ws,
            run_id=self.run.id,
            well_id=(well or self.w2).id,
            channel_key="ratio",
            source=MeltingStepSource.MANUAL,
            value=70.0,
            status=MeltingStepStatus.ACCEPTED,
            assigned_window=window,
            version=version,
        )
        self.steps.append(peak)
        return peak

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

    def assign_cmd(self, **kw):  # type: ignore[no-untyped-def]
        base = dict(workspace_id=self.ws, step_id=self.step.id, expected_version=1, window="Main")
        return AssignMeltingStepCommand(**{**base, **kw})

    async def do_accept(self, *steps, auth=None):  # type: ignore[no-untyped-def]
        """Accept the peaks given, each as the peak (read at its version) or (id, version)."""
        cmd = AcceptMeltingStepsCommand(
            workspace_id=self.ws,
            run_id=self.run.id,
            steps=tuple(s if isinstance(s, tuple) else (s.id, s.version) for s in steps),
        )
        return await self.accept(cmd, auth=auth or self.auth)

    async def do_add(self, auth=None, **kw):  # type: ignore[no-untyped-def]
        return await self.add(self.add_cmd(**kw), auth=auth or self.auth)

    async def do_review(self, auth=None, **kw):  # type: ignore[no-untyped-def]
        return await self.review(self.review_cmd(**kw), auth=auth or self.auth)

    async def do_assign(self, auth=None, **kw):  # type: ignore[no-untyped-def]
        return await self.assign(self.assign_cmd(**kw), auth=auth or self.auth)

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
        ("status", AuditAction.CREATE, "accepted"),
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


async def test_add_allowed_on_a_completed_run():
    h = Harness(status=RunStatus.COMPLETED)
    out = (await h.do_add()).unwrap()
    assert out.recalculated and h.uow.committed
    h.step_repo.add.assert_awaited_once_with(out.step)


async def test_review_allowed_on_a_completed_run():
    h = Harness(status=RunStatus.COMPLETED)
    out = (await h.do_review(status=MeltingStepStatus.REJECTED, reason="noise")).unwrap()
    assert out.recalculated and out.step.status is MeltingStepStatus.REJECTED
    assert h.uow.committed


@pytest.mark.parametrize("which", ["add", "review"])
async def test_approved_run_refuses_step_changes(which):
    h = Harness(status=RunStatus.APPROVED)
    out = await (h.do_add() if which == "add" else h.do_review())
    failure = out.failure()
    assert isinstance(failure, ConflictError) and str(failure) == NOT_EDITABLE
    h.assert_nothing_written()


@pytest.mark.parametrize("which", ["add", "review"])
@pytest.mark.parametrize("status", [RunStatus.DRAFT, RunStatus.APPROVED])
async def test_locked_run_refuses_step_changes(which, status):
    h = Harness(status=status, locked=True)
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


async def test_add_on_a_position_of_another_run_is_not_found():
    h = Harness()
    _, (other, _, _) = _instrument_run()
    failure = (await h.do_add(well_id=other.id)).failure()
    assert isinstance(failure, NotFoundError)
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
    assert isinstance((await h.do_assign()).failure(), NotFoundError)
    h.step_repo.find_by_id.return_value = None
    h.run_repo.find_by_id_in_workspace.return_value = h.run
    assert isinstance((await h.do_assign()).failure(), NotFoundError)
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
    with pytest.raises(AuthorizationError):
        await h.do_assign(auth=viewer)
    h.assert_nothing_written()


async def test_other_workspace_is_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h.do_add(auth=FakeAuth())
    with pytest.raises(NotFoundError):
        await h.do_review(auth=FakeAuth())
    with pytest.raises(NotFoundError):
        await h.do_assign(auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()
    h.step_repo.find_by_id.assert_not_awaited()


# ---------------------------------------------------------------------------
# Assigning a peak to a temperature window
# ---------------------------------------------------------------------------


def _changes(record_kwargs):  # type: ignore[no-untyped-def]
    return {(e.field_name, e.old_value, e.new_value) for e in record_kwargs["entries"]}


async def test_assign_names_the_peak_and_recalculates():
    h = Harness()
    out = (await h.do_assign(window="Main", reason="  merged by the ligand ")).unwrap()
    assert out == MeltingStepChange(h.step, True)
    step = out.step
    assert step.assigned_window == "Main" and step.assignment_reason == "merged by the ligand"
    assert step.assigned_by == h.auth.user_id and step.assigned_at is not None
    assert step.status is MeltingStepStatus.ACCEPTED
    h.step_repo.update.assert_awaited_once_with(step, expected_version=1)
    kw = h.audit.record.await_args.kwargs
    assert kw["operation_type"] is OperationType.PROPERTY_EDIT
    assert kw["entity_type"] == "MeltingStep" and kw["entity_id"] == step.id
    assert kw["user_id"] == h.auth.user_id and kw["session"] is h.uow.session
    assert kw["reason"] == "merged by the ligand"
    assert _changes(kw) == {
        ("assigned_window", None, "Main"),
        ("assignment_reason", None, "merged by the ligand"),
        ("status", "unreviewed", "accepted"),
    }
    assert all(e.action is AuditAction.UPDATE for e in kw["entries"])
    assert h.uow.committed
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)


async def test_assign_needs_no_reason():
    h = Harness()
    out = (await h.do_assign(window="Low")).unwrap()
    assert out.step.assigned_window == "Low" and out.step.assignment_reason is None
    assert h.audit.record.await_args.kwargs["reason"] is None


@pytest.mark.parametrize("window", ["Nope", "Other", " "])
async def test_assign_unknown_window_refused(window):
    """Not a window at all, a window of another signal, and a blank name."""
    h = Harness()
    failure = (await h.do_assign(window=window)).failure()
    assert isinstance(failure, ValidationError)
    assert str(failure) == f"'{window}' is not a window on this signal"
    assert h.step.assigned_window is None
    h.assert_nothing_written()


async def test_assign_replaces_the_window_s_previous_peak_and_audits_both():
    h = Harness()
    previous = h.peak(window="Main", version=3)
    in_low = h.peak(window="Low")
    elsewhere = h.peak(h.w1, window="Main")
    out = (await h.do_assign(window="Main", reason="the real one")).unwrap()

    assert out.recalculated and out.step is h.step
    assert previous.assigned_window is None and previous.assigned_by is None
    assert previous.status is MeltingStepStatus.ACCEPTED
    assert (in_low.assigned_window, elsewhere.assigned_window) == ("Low", "Main")
    assert [c.args[0] for c in h.step_repo.update.await_args_list] == [h.step, previous]
    assert h.step_repo.update.await_args_list[1].kwargs == {"expected_version": 3}
    records = {c.kwargs["entity_id"]: c.kwargs for c in h.audit.record.await_args_list}
    assert set(records) == {h.step.id, previous.id}
    released = records[previous.id]
    assert released["operation_type"] is OperationType.PROPERTY_EDIT
    assert released["reason"] == "the real one" and released["session"] is h.uow.session
    assert _changes(released) == {("assigned_window", "Main", None)}
    assert h.uow.committed
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)


async def test_assign_again_still_releases_a_second_peak_of_the_window():
    """Two peaks assigned to one window (direct data edits): assigning one again mends it."""
    h = Harness()
    h.step.assign(window="Main", reason=None, by=h.auth.user_id)
    other = h.peak(window="Main")
    out = (await h.do_assign(window="Main", expected_version=2)).unwrap()
    assert out.recalculated and other.assigned_window is None
    h.step_repo.update.assert_awaited_once_with(other, expected_version=1)
    assert h.audit.record.await_args.kwargs["entity_id"] == other.id


async def test_assign_same_window_again_writes_nothing():
    h = Harness()
    h.step.assign(window="Main", reason=None, by=h.auth.user_id)
    out = (await h.do_assign(window="Main", expected_version=2)).unwrap()
    assert out == MeltingStepChange(h.step, False)
    h.assert_nothing_written()


async def test_clear_assignment():
    h = Harness()
    h.step.assign(window="Main", reason="first guess", by=h.auth.user_id)
    out = (await h.do_assign(window=None, reason=" wrong peak ", expected_version=2)).unwrap()
    step = out.step
    assert out.recalculated
    assert (step.assigned_window, step.assignment_reason, step.assigned_by) == (None, None, None)
    assert step.status is MeltingStepStatus.ACCEPTED  # clearing leaves the status alone
    h.step_repo.update.assert_awaited_once_with(step, expected_version=2)
    kw = h.audit.record.await_args.kwargs
    # The peak keeps no reason once cleared: the audit record is where it is kept.
    assert kw["reason"] == "wrong peak"
    assert _changes(kw) == {
        ("assigned_window", "Main", None),
        ("assignment_reason", "first guess", None),
    }
    h.protocol_repo.find_by_id_in_workspace.assert_not_awaited()
    h.step_repo.find_by_run.assert_not_awaited()


async def test_assign_stale_version_conflicts():
    h = Harness()
    h.step_repo.update.side_effect = ConflictError("changed by someone else")
    failure = (await h.do_assign(expected_version=1)).failure()
    assert isinstance(failure, ConflictError)
    h.audit.record.assert_not_awaited()
    assert h.uow.committed is False
    h.engine.compute_for_run.assert_not_awaited()


async def test_assign_reason_too_long_is_validation_error():
    h = Harness()
    failure = (await h.do_assign(reason="x" * 501)).failure()
    assert isinstance(failure, ValidationError)
    h.assert_nothing_written()


async def test_assign_allowed_on_a_completed_run():
    h = Harness(status=RunStatus.COMPLETED)
    out = (await h.do_assign()).unwrap()
    assert out.recalculated and out.step.assigned_window == "Main"
    assert h.uow.committed


async def test_assign_refused_on_an_approved_run():
    h = Harness(status=RunStatus.APPROVED)
    failure = (await h.do_assign()).failure()
    assert isinstance(failure, ConflictError) and str(failure) == NOT_EDITABLE
    h.assert_nothing_written()


@pytest.mark.parametrize("window", ["Main", None])
async def test_assign_refused_on_a_locked_run(window):
    h = Harness(locked=True)
    failure = (await h.do_assign(window=window)).failure()
    assert isinstance(failure, ConflictError) and str(failure) == "This run is locked"
    h.assert_nothing_written()


async def test_assign_engine_failure_becomes_compute_warning():
    h = Harness()
    h.engine.compute_for_run.return_value = Failure(ValidationError("boom"))
    out = (await h.do_assign()).unwrap()
    assert out.recalculated is False and h.uow.committed
    assert out.compute_warning == (
        "The peak was saved, but the calculations could not be updated. "
        "Select Recompute on the run to update them."
    )


async def test_add_with_window_assigns_in_one_save():
    h = Harness()
    previous = h.peak(window="Main", version=2)
    out = (await h.do_add(assigned_window="Main", reason=" shoulder ")).unwrap()
    step = out.step
    assert out.recalculated
    assert (step.reason, step.assignment_reason) == ("shoulder", "shoulder")
    assert step.assigned_window == "Main" and step.assigned_by == h.auth.user_id
    h.step_repo.add.assert_awaited_once_with(step)
    records = {c.kwargs["entity_id"]: c.kwargs for c in h.audit.record.await_args_list}
    assert set(records) == {step.id, previous.id}
    created = records[step.id]
    assert created["operation_type"] is OperationType.DATA_ENTRY
    assert {(e.field_name, e.action, e.new_value) for e in created["entries"]} == {
        ("value", AuditAction.CREATE, "60"),
        ("status", AuditAction.CREATE, "accepted"),
        ("assigned_window", AuditAction.CREATE, "Main"),
    }
    # The window's previous peak gives way in the same save.
    assert previous.assigned_window is None
    h.step_repo.update.assert_awaited_once_with(previous, expected_version=2)
    assert records[previous.id]["operation_type"] is OperationType.PROPERTY_EDIT
    assert records[previous.id]["reason"] == "shoulder"
    assert _changes(records[previous.id]) == {("assigned_window", "Main", None)}
    assert h.uow.committed


async def test_add_with_unknown_window_refused():
    h = Harness()
    failure = (await h.do_add(assigned_window="Other")).failure()
    assert isinstance(failure, ValidationError)
    assert str(failure) == "'Other' is not a window on this signal"
    h.assert_nothing_written()


async def test_add_without_window_does_not_read_the_protocol():
    h = Harness()
    out = (await h.do_add()).unwrap()
    assert out.step.assigned_window is None
    h.protocol_repo.find_by_id_in_workspace.assert_not_awaited()
    h.step_repo.find_by_run.assert_not_awaited()


# ---------------------------------------------------------------------------
# Accepting many peaks of a run in one request
# ---------------------------------------------------------------------------


def _unreviewed(h: Harness) -> MeltingStep:
    """A second unreviewed instrument peak of the run, on the other position."""
    peak = MeltingStep(
        workspace_id=h.ws,
        run_id=h.run.id,
        well_id=h.w1.id,
        channel_key="ratio",
        source=MeltingStepSource.INSTRUMENT,
        value=61.0,
        instrument_value=61.0,
        instrument_label="T1",
    )
    h.steps.append(peak)
    return peak


def _rejected(h: Harness) -> MeltingStep:
    peak = h.peak()
    peak.status, peak.reason = MeltingStepStatus.REJECTED, "bubble"
    return peak


async def test_accept_many_changes_the_unreviewed_and_skips_the_rest():
    h = Harness()
    other, accepted, rejected = _unreviewed(h), h.peak(version=4), _rejected(h)
    # A stale version on a peak that does not change is not looked at.
    out = (await h.do_accept(h.step, (accepted.id, 1), other, (rejected.id, 9))).unwrap()

    assert out == MeltingStepsAccepted((h.step, other), 2, True)
    assert out.compute_warning is None
    for peak in (h.step, other):
        assert (peak.status, peak.version) == (MeltingStepStatus.ACCEPTED, 2)
        assert peak.changed_by == h.auth.user_id and peak.reason is None
    assert (accepted.status, accepted.version) == (MeltingStepStatus.ACCEPTED, 4)
    assert (rejected.status, rejected.reason) == (MeltingStepStatus.REJECTED, "bubble")
    assert [c.args[0] for c in h.step_repo.update.await_args_list] == [h.step, other]
    assert {c.kwargs["expected_version"] for c in h.step_repo.update.await_args_list} == {1}
    # One audit record per changed peak, as the single accept writes it.
    records = [c.kwargs for c in h.audit.record.await_args_list]
    assert [kw["entity_id"] for kw in records] == [h.step.id, other.id]
    for kw in records:
        assert kw["operation_type"] is OperationType.PROPERTY_EDIT
        assert (kw["entity_type"], kw["reason"]) == ("MeltingStep", None)
        assert kw["user_id"] == h.auth.user_id and kw["session"] is h.uow.session
        assert [(e.field_name, e.action, e.old_value, e.new_value) for e in kw["entries"]] == [
            ("status", AuditAction.UPDATE, "unreviewed", "accepted")
        ]
    assert h.uow.committed
    # One recalculation for the whole request.
    h.engine.compute_for_run.assert_awaited_once_with(h.run.id, workspace_id=h.ws)
    h.step_repo.find_by_run.assert_awaited_once_with(h.ws, h.run.id)
    h.curve_repo.find_by_wells.assert_not_awaited()


async def test_accept_many_writes_the_same_audit_record_as_the_single_accept():
    one, many = Harness(), Harness()
    (await one.do_review()).unwrap()
    (await many.do_accept(many.step)).unwrap()
    single, bulk = one.audit.record.await_args.kwargs, many.audit.record.await_args.kwargs
    assert single.keys() == bulk.keys()
    for kw in (single, bulk):
        assert (kw["operation_type"], kw["entity_type"]) == (
            OperationType.PROPERTY_EDIT,
            "MeltingStep",
        )
        assert kw["reason"] is None
        assert [
            (e.entity_type, e.field_name, e.action, e.old_value, e.new_value)
            for e in kw["entries"]
        ] == [("MeltingStep", "status", AuditAction.UPDATE, "unreviewed", "accepted")]


async def test_accept_many_with_a_peak_that_is_not_the_runs_is_not_found():
    h = Harness()
    stranger = uuid.uuid4()
    failure = (await h.do_accept(h.step, (stranger, 1))).failure()
    assert isinstance(failure, NotFoundError) and str(stranger) in str(failure)
    assert (h.step.status, h.step.version) == (MeltingStepStatus.UNREVIEWED, 1)
    h.assert_nothing_written()


async def test_accept_many_with_a_stale_version_fails_the_whole_request():
    h = Harness()
    other = _unreviewed(h)
    h.step_repo.update.side_effect = [None, ConflictError("changed by someone else")]
    result = await h.do_accept(h.step, (other.id, 7))
    assert isinstance(result, Failure) and isinstance(result.failure(), ConflictError)
    assert h.step_repo.update.await_args_list[1].kwargs == {"expected_version": 7}
    # The first peak's write is never committed, and nothing is recalculated.
    assert h.uow.committed is False
    h.engine.compute_for_run.assert_not_awaited()


@pytest.mark.parametrize(
    ("status", "locked", "message"),
    [
        (RunStatus.APPROVED, False, NOT_EDITABLE),
        (RunStatus.DRAFT, True, "This run is locked"),
    ],
)
async def test_accept_many_refused_on_an_approved_or_locked_run(status, locked, message):
    h = Harness(status=status, locked=locked)
    failure = (await h.do_accept(h.step)).failure()
    assert isinstance(failure, ConflictError) and failure.message == message
    h.step_repo.find_by_run.assert_not_awaited()
    h.assert_nothing_written()


async def test_accept_many_allowed_on_a_completed_run():
    h = Harness(status=RunStatus.COMPLETED)
    assert (await h.do_accept(h.step)).unwrap().recalculated


async def test_accept_many_with_nothing_to_change_writes_nothing():
    h = Harness()
    accepted, rejected = h.peak(), _rejected(h)
    out = (await h.do_accept(accepted, rejected)).unwrap()
    assert out == MeltingStepsAccepted((), 2, False)
    h.assert_nothing_written()


async def test_accept_many_engine_failure_becomes_compute_warning():
    h = Harness()
    h.engine.compute_for_run.return_value = Failure(ValidationError("bad formula"))
    out = (await h.do_accept(h.step, _unreviewed(h))).unwrap()
    assert (out.recalculated, out.compute_warning) == (False, PEAKS_COMPUTE_FAILED)
    assert PEAKS_COMPUTE_FAILED.startswith("The peaks were saved, but")
    assert len(out.steps) == 2 and h.uow.committed


async def test_accept_many_run_not_found():
    h = Harness()
    h.run_repo.find_by_id_in_workspace.return_value = None
    assert isinstance((await h.do_accept(h.step)).failure(), NotFoundError)
    h.assert_nothing_written()


async def test_accept_many_needs_an_editor_of_the_workspace():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h.do_accept(h.step, auth=FakeAuth(role="viewer", workspace_id=h.ws))
    with pytest.raises(NotFoundError):
        await h.do_accept(h.step, auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()
    h.assert_nothing_written()
