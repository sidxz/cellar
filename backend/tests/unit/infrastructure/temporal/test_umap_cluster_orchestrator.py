"""Null + Temporal orchestrator behavior for umap-cluster.

The Null path (TEMPORAL_DISABLED=1 / tests) runs the runner inline as a
fire-and-forget task. The Temporal path passes UUIDs directly in the workflow
input (the workflow input dataclass holds UUID fields). The Null orchestrator
records FAILED itself when the runner raises (the runner leaves FAILED-marking
to the boundary).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.umap_cluster import (
    NullUmapClusterOrchestrator,
    TemporalUmapClusterOrchestrator,
)


class FakeRunner:
    def __init__(self):
        self.calls: list[dict] = []
        self.done = asyncio.Event()

    async def execute(
        self, *, job_id, workspace_id, molecule_ids, picker, picker_params
    ):
        self.calls.append(
            {
                "job_id": job_id,
                "workspace_id": workspace_id,
                "molecule_ids": molecule_ids,
                "picker": picker,
                "picker_params": picker_params,
            }
        )
        self.done.set()


@pytest.mark.asyncio
async def test_null_orchestrator_invokes_runner_inline():
    runner = FakeRunner()
    orch = NullUmapClusterOrchestrator(runner=runner.execute)
    job_id, ws = uuid.uuid4(), uuid.uuid4()
    mol_ids = [uuid.uuid4(), uuid.uuid4()]
    await orch.schedule(
        job_id=job_id,
        workspace_id=ws,
        molecule_ids=mol_ids,
        picker="maxmin",
        picker_params={"n": 5},
    )
    await asyncio.wait_for(runner.done.wait(), timeout=1.0)
    assert runner.calls[0]["job_id"] == job_id
    assert runner.calls[0]["workspace_id"] == ws
    assert runner.calls[0]["molecule_ids"] == mol_ids
    assert runner.calls[0]["picker"] == "maxmin"
    assert runner.calls[0]["picker_params"] == {"n": 5}


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    async def _noop(**_kwargs):
        pass

    orch = NullUmapClusterOrchestrator(runner=_noop)
    await orch.cancel(job_id=uuid.uuid4())  # must not raise


class BoomRunner:
    async def execute(self, *, job_id, workspace_id, molecule_ids, picker, picker_params):
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
    boom = BoomRunner()
    spy = SpyMarkFailed()
    orch = NullUmapClusterOrchestrator(runner=boom.execute, mark_failed=spy)
    job_id = uuid.uuid4()
    await orch.schedule(
        job_id=job_id,
        workspace_id=uuid.uuid4(),
        molecule_ids=[],
        picker="maxmin",
        picker_params={},
    )
    await asyncio.gather(*list(orch._tasks))  # swallowed after recording — no raise
    assert len(spy.calls) == 1
    assert spy.calls[0].job_id == job_id


class FakeClient:
    def __init__(self):
        self.started: list[dict] = []

    async def start_workflow(self, run_fn, arg, *, id, task_queue):
        self.started.append({"arg": arg, "id": id, "task_queue": task_queue})


@pytest.mark.asyncio
async def test_temporal_orchestrator_passes_uuids_in_payload():
    client = FakeClient()
    orch = TemporalUmapClusterOrchestrator(client=client)
    job_id, ws = uuid.uuid4(), uuid.uuid4()
    mids = [uuid.uuid4(), uuid.uuid4()]
    await orch.schedule(
        job_id=job_id,
        workspace_id=ws,
        molecule_ids=mids,
        picker="butina",
        picker_params={"threshold": 0.4},
    )
    started = client.started[0]
    assert started["id"] == f"umap-cluster-{job_id}"
    # UmapClusterWorkflowInput holds UUID fields (not str), unlike scaffold-tree
    assert started["arg"].job_id == job_id
    assert started["arg"].workspace_id == ws
    assert started["arg"].molecule_ids == mids
    assert started["arg"].picker == "butina"
    assert started["arg"].picker_params == {"threshold": 0.4}
