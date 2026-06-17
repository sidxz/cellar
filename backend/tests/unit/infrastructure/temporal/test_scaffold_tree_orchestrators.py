"""Null + Temporal orchestrator behavior for scaffold-tree.

The Null path (TEMPORAL_DISABLED=1 / tests) runs the runner inline as a
fire-and-forget task. The Temporal path converts UUIDs to strings and starts the
workflow on the main task queue. The Null orchestrator records FAILED itself when
the runner raises (the runner leaves FAILED-marking to the boundary).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.scaffold_tree import (
    NullScaffoldTreeOrchestrator,
    TemporalScaffoldTreeOrchestrator,
)


class FakeRunner:
    def __init__(self):
        self.calls: list[dict] = []
        self.done = asyncio.Event()

    async def run(self, *, job_id, workspace_id, molecule_ids):
        self.calls.append(
            {
                "job_id": job_id,
                "workspace_id": workspace_id,
                "molecule_ids": molecule_ids,
            }
        )
        self.done.set()


@pytest.mark.asyncio
async def test_null_orchestrator_invokes_runner_inline():
    runner = FakeRunner()
    orch = NullScaffoldTreeOrchestrator(runner)
    job_id, ws = uuid.uuid4(), uuid.uuid4()
    mol_ids = [uuid.uuid4(), uuid.uuid4()]
    await orch.schedule(job_id=job_id, workspace_id=ws, molecule_ids=mol_ids)
    await asyncio.wait_for(runner.done.wait(), timeout=1.0)
    assert runner.calls[0]["job_id"] == job_id
    assert runner.calls[0]["workspace_id"] == ws
    assert runner.calls[0]["molecule_ids"] == mol_ids


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    orch = NullScaffoldTreeOrchestrator(FakeRunner())
    await orch.cancel(job_id=uuid.uuid4())  # must not raise


class BoomRunner:
    async def run(self, *, job_id, workspace_id, molecule_ids):
        raise RuntimeError("runner boom")


class SpyMarkFailed:
    def __init__(self):
        self.calls = []

    async def execute(self, payload):
        self.calls.append(payload)


@pytest.mark.asyncio
async def test_null_orchestrator_marks_failed_when_runner_raises():
    # No Temporal workflow on the inline path, so the Null orchestrator records
    # FAILED itself; the background task must not propagate the error.
    spy = SpyMarkFailed()
    orch = NullScaffoldTreeOrchestrator(BoomRunner(), mark_failed=spy)
    job_id = uuid.uuid4()
    await orch.schedule(job_id=job_id, workspace_id=uuid.uuid4(), molecule_ids=[])
    await asyncio.gather(*list(orch._tasks))  # swallowed after recording — no raise
    assert len(spy.calls) == 1
    assert spy.calls[0].job_id == job_id


class FakeClient:
    def __init__(self):
        self.started: list[dict] = []

    async def start_workflow(self, run_fn, arg, *, id, task_queue):
        self.started.append({"arg": arg, "id": id, "task_queue": task_queue})


@pytest.mark.asyncio
async def test_temporal_orchestrator_serializes_uuids_to_strings():
    client = FakeClient()
    orch = TemporalScaffoldTreeOrchestrator(client)
    job_id, ws = uuid.uuid4(), uuid.uuid4()
    mids = [uuid.uuid4(), uuid.uuid4()]
    await orch.schedule(job_id=job_id, workspace_id=ws, molecule_ids=mids)
    started = client.started[0]
    assert started["id"] == f"scaffold-tree-{job_id}"
    assert started["arg"].job_id == str(job_id)
    assert started["arg"].workspace_id == str(ws)
    assert started["arg"].molecule_ids == [str(m) for m in mids]
