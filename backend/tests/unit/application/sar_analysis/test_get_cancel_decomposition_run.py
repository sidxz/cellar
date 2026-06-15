from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Failure, Success

from cellar.application.sar_analysis.cancel_decomposition_run import (
    CancelDecompositionRun,
    CancelDecompositionRunInput,
)
from cellar.application.sar_analysis.get_decomposition_run import (
    GetDecompositionRun,
    GetDecompositionRunInput,
)
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRunRepo:
    def __init__(self, run: RGroupDecompositionRun | None = None) -> None:
        self._runs: dict[uuid.UUID, RGroupDecompositionRun] = {}
        if run is not None:
            self._runs[run.id] = run

    async def save(self, run):
        self._runs[run.id] = run

    async def find_by_id(self, run_id, *, workspace_id):
        run = self._runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return None
        return run


class FakeOrchestrator:
    def __init__(self):
        self.cancelled: list[uuid.UUID] = []

    async def cancel(self, *, run_id):
        self.cancelled.append(run_id)


def _pending(ws):
    return RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    )


@pytest.mark.asyncio
async def test_get_returns_run():
    ws = uuid.uuid4()
    run = _pending(ws)
    uc = GetDecompositionRun(repository=FakeRunRepo(run), uow=FakeUoW())
    out = await uc.execute(GetDecompositionRunInput(run_id=run.id, workspace_id=ws))
    assert isinstance(out, Success)
    assert out.unwrap().id == run.id


@pytest.mark.asyncio
async def test_get_missing_is_failure():
    uc = GetDecompositionRun(repository=FakeRunRepo(), uow=FakeUoW())
    out = await uc.execute(GetDecompositionRunInput(run_id=uuid.uuid4(), workspace_id=uuid.uuid4()))
    assert isinstance(out, Failure)


@pytest.mark.asyncio
async def test_get_other_workspace_is_failure():
    ws = uuid.uuid4()
    run = _pending(ws)
    uc = GetDecompositionRun(repository=FakeRunRepo(run), uow=FakeUoW())
    out = await uc.execute(GetDecompositionRunInput(run_id=run.id, workspace_id=uuid.uuid4()))
    assert isinstance(out, Failure)


@pytest.mark.asyncio
async def test_cancel_marks_cancelled_and_forwards_to_orchestrator():
    ws = uuid.uuid4()
    run = _pending(ws)
    repo = FakeRunRepo(run)
    orch = FakeOrchestrator()
    uc = CancelDecompositionRun(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelDecompositionRunInput(run_id=run.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert out.unwrap().status == RGroupDecompositionRunStatus.CANCELLED
    assert orch.cancelled == [run.id]


@pytest.mark.asyncio
async def test_cancel_terminal_run_is_idempotent_no_op():
    ws = uuid.uuid4()
    ready = _pending(ws).mark_running(_NOW).mark_ready(
        rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    repo = FakeRunRepo(ready)
    orch = FakeOrchestrator()
    uc = CancelDecompositionRun(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelDecompositionRunInput(run_id=ready.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert out.unwrap().status == RGroupDecompositionRunStatus.READY  # unchanged
    assert orch.cancelled == []  # terminal cancel must not signal the orchestrator


@pytest.mark.asyncio
async def test_cancel_missing_is_failure():
    uc = CancelDecompositionRun(repository=FakeRunRepo(), orchestrator=FakeOrchestrator(), uow=FakeUoW())
    out = await uc.execute(
        CancelDecompositionRunInput(run_id=uuid.uuid4(), workspace_id=uuid.uuid4(), now=_NOW)
    )
    assert isinstance(out, Failure)
