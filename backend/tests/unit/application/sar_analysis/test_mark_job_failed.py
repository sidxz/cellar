from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.mark_activity_projection_failed import (
    MarkActivityProjectionFailed,
    MarkActivityProjectionFailedInput,
)
from cellar.application.sar_analysis.mark_decomposition_run_failed import (
    MarkDecompositionRunFailed,
    MarkDecompositionRunFailedInput,
)
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeProjRepo:
    def __init__(self, proj=None):
        self._by_id = {proj.id: proj} if proj else {}

    async def save(self, p):
        self._by_id[p.id] = p

    async def find_by_id(self, pid, *, workspace_id):
        p = self._by_id.get(pid)
        return p if p and p.workspace_id == workspace_id else None


class FakeRunRepo:
    def __init__(self, run=None):
        self._by_id = {run.id: run} if run else {}

    async def save(self, r):
        self._by_id[r.id] = r

    async def find_by_id(self, rid, *, workspace_id):
        r = self._by_id.get(rid)
        return r if r and r.workspace_id == workspace_id else None


def _running_proj(ws):
    return SarActivityProjection.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
    ).mark_running(_NOW)


def _running_run(ws):
    return RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    ).mark_running(_NOW)


@pytest.mark.asyncio
async def test_mark_projection_failed_from_running():
    ws = uuid.uuid4()
    proj = _running_proj(ws)
    repo = FakeProjRepo(proj)
    uc = MarkActivityProjectionFailed(repository=repo, uow=FakeUoW())
    await uc.execute(
        MarkActivityProjectionFailedInput(projection_id=proj.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[proj.id].status == SarActivityProjectionStatus.FAILED
    assert repo._by_id[proj.id].error_message == "boom"


@pytest.mark.asyncio
async def test_mark_projection_failed_idempotent_on_terminal():
    # A cancel that won the race must NOT be flipped to FAILED — terminal is left as-is.
    ws = uuid.uuid4()
    cancelled = _running_proj(ws).mark_cancelled(_NOW)
    repo = FakeProjRepo(cancelled)
    uc = MarkActivityProjectionFailed(repository=repo, uow=FakeUoW())
    await uc.execute(
        MarkActivityProjectionFailedInput(projection_id=cancelled.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[cancelled.id].status == SarActivityProjectionStatus.CANCELLED


@pytest.mark.asyncio
async def test_mark_projection_failed_missing_is_noop():
    ws = uuid.uuid4()
    repo = FakeProjRepo()
    uc = MarkActivityProjectionFailed(repository=repo, uow=FakeUoW())
    await uc.execute(
        MarkActivityProjectionFailedInput(projection_id=uuid.uuid4(), workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id == {}


@pytest.mark.asyncio
async def test_mark_run_failed_from_running():
    ws = uuid.uuid4()
    run = _running_run(ws)
    repo = FakeRunRepo(run)
    uc = MarkDecompositionRunFailed(repository=repo, uow=FakeUoW())
    await uc.execute(
        MarkDecompositionRunFailedInput(run_id=run.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[run.id].status == RGroupDecompositionRunStatus.FAILED
    assert repo._by_id[run.id].error_message == "boom"


@pytest.mark.asyncio
async def test_mark_run_failed_idempotent_on_terminal():
    ws = uuid.uuid4()
    cancelled = _running_run(ws).mark_cancelled(_NOW)
    repo = FakeRunRepo(cancelled)
    uc = MarkDecompositionRunFailed(repository=repo, uow=FakeUoW())
    await uc.execute(
        MarkDecompositionRunFailedInput(run_id=cancelled.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[cancelled.id].status == RGroupDecompositionRunStatus.CANCELLED
