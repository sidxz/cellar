from __future__ import annotations

import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.sar_activity_projection import (
    NullSarActivityProjectionOrchestrator,
)


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def run(self, *, run_id, workspace_id, channel_spec, collection_id=None, molecule_ids=None):
        self.calls.append(
            {"run_id": run_id, "channel_spec": channel_spec, "collection_id": collection_id, "molecule_ids": molecule_ids}
        )


@pytest.mark.asyncio
async def test_null_orchestrator_runs_inline_as_background_task():
    runner = FakeRunner()
    orch = NullSarActivityProjectionOrchestrator(runner)
    pid = uuid.uuid4()
    await orch.schedule(
        projection_id=pid, workspace_id=uuid.uuid4(),
        channel_spec={"column": "drc:x"}, collection_id=uuid.uuid4(),
    )
    assert orch._tasks, "schedule should have spawned a background task"
    await asyncio.gather(*list(orch._tasks))
    assert runner.calls and runner.calls[0]["run_id"] == pid
    assert runner.calls[0]["channel_spec"] == {"column": "drc:x"}


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    orch = NullSarActivityProjectionOrchestrator(FakeRunner())
    assert await orch.cancel(projection_id=uuid.uuid4()) is None


class BoomRunner:
    async def run(self, *, run_id, workspace_id, channel_spec, collection_id=None, molecule_ids=None):
        raise RuntimeError("runner boom")


class SpyMarkFailed:
    def __init__(self):
        self.calls = []

    async def execute(self, payload):
        self.calls.append(payload)


@pytest.mark.asyncio
async def test_null_orchestrator_marks_failed_when_runner_raises():
    # The inline path has no Temporal workflow to mark FAILED on exhaustion, so
    # the Null orchestrator records it. The background task must not propagate.
    spy = SpyMarkFailed()
    orch = NullSarActivityProjectionOrchestrator(BoomRunner(), mark_failed=spy)
    pid = uuid.uuid4()
    await orch.schedule(projection_id=pid, workspace_id=uuid.uuid4(), channel_spec={"column": "drc:x"})
    await asyncio.gather(*list(orch._tasks))  # swallowed after recording — no raise
    assert len(spy.calls) == 1
    assert spy.calls[0].job_id == pid
