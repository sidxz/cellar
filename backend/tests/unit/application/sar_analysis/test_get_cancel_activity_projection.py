from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Failure, Success

from cellar.application.sar_analysis.cancel_activity_projection import (
    CancelActivityProjection,
    CancelActivityProjectionInput,
)
from cellar.application.sar_analysis.get_activity_projection import (
    GetActivityProjection,
    GetActivityProjectionInput,
)
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRepo:
    def __init__(self, proj=None):
        self._by_id = {proj.id: proj} if proj else {}

    async def save(self, p):
        self._by_id[p.id] = p

    async def find_by_id(self, pid, *, workspace_id):
        p = self._by_id.get(pid)
        return p if p and p.workspace_id == workspace_id else None


class FakeOrchestrator:
    def __init__(self):
        self.cancelled = []

    async def schedule(self, **kw):
        pass

    async def cancel(self, *, projection_id):
        self.cancelled.append(projection_id)


def _pending(ws):
    return SarActivityProjection.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
    )


@pytest.mark.asyncio
async def test_get_returns_projection():
    ws = uuid.uuid4()
    proj = _pending(ws)
    uc = GetActivityProjection(repository=FakeRepo(proj), uow=FakeUoW())
    out = await uc.execute(GetActivityProjectionInput(projection_id=proj.id, workspace_id=ws))
    assert isinstance(out, Success)
    assert out.unwrap().id == proj.id


@pytest.mark.asyncio
async def test_get_missing_is_failure():
    uc = GetActivityProjection(repository=FakeRepo(None), uow=FakeUoW())
    out = await uc.execute(GetActivityProjectionInput(projection_id=uuid.uuid4(), workspace_id=uuid.uuid4()))
    assert isinstance(out, Failure)


@pytest.mark.asyncio
async def test_cancel_marks_cancelled_and_signals_orchestrator():
    ws = uuid.uuid4()
    proj = _pending(ws)
    repo = FakeRepo(proj)
    orch = FakeOrchestrator()
    uc = CancelActivityProjection(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelActivityProjectionInput(projection_id=proj.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert repo._by_id[proj.id].status == SarActivityProjectionStatus.CANCELLED
    assert orch.cancelled == [proj.id]


@pytest.mark.asyncio
async def test_cancel_already_terminal_is_idempotent_noop():
    ws = uuid.uuid4()
    ready = _pending(ws).mark_running(_NOW).mark_ready(value_count=0, now=_NOW)
    repo = FakeRepo(ready)
    orch = FakeOrchestrator()
    uc = CancelActivityProjection(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelActivityProjectionInput(projection_id=ready.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert repo._by_id[ready.id].status == SarActivityProjectionStatus.READY  # unchanged


@pytest.mark.asyncio
async def test_cancel_missing_is_failure():
    uc = CancelActivityProjection(repository=FakeRepo(None), orchestrator=FakeOrchestrator(), uow=FakeUoW())
    out = await uc.execute(CancelActivityProjectionInput(projection_id=uuid.uuid4(), workspace_id=uuid.uuid4(), now=_NOW))
    assert isinstance(out, Failure)
