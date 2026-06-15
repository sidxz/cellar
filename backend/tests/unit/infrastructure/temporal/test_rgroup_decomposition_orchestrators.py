"""Null + Temporal orchestrator behavior for R-group decomposition.

The Null path (TEMPORAL_DISABLED=1 / tests) runs the runner inline as a
fire-and-forget task. The Temporal path converts UUIDs to strings and starts the
workflow on the main task queue.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.rgroup_decomposition import (
    NullRGroupDecompositionOrchestrator,
    TemporalRGroupDecompositionOrchestrator,
)


class FakeRunner:
    def __init__(self):
        self.calls: list[dict] = []
        self.done = asyncio.Event()

    async def run(self, *, run_id, workspace_id, core_smiles, collection_id=None, molecule_ids=None):
        self.calls.append(
            {
                "run_id": run_id,
                "workspace_id": workspace_id,
                "core_smiles": core_smiles,
                "collection_id": collection_id,
                "molecule_ids": molecule_ids,
            }
        )
        self.done.set()


@pytest.mark.asyncio
async def test_null_orchestrator_runs_runner_inline():
    runner = FakeRunner()
    orch = NullRGroupDecompositionOrchestrator(runner)
    run_id, ws, cid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await orch.schedule(run_id=run_id, workspace_id=ws, core_smiles="c1ccccc1", collection_id=cid)
    await asyncio.wait_for(runner.done.wait(), timeout=1.0)
    assert runner.calls[0]["run_id"] == run_id
    assert runner.calls[0]["collection_id"] == cid


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    orch = NullRGroupDecompositionOrchestrator(FakeRunner())
    await orch.cancel(run_id=uuid.uuid4())  # must not raise


class FakeClient:
    def __init__(self):
        self.started: list[dict] = []

    async def start_workflow(self, run_fn, arg, *, id, task_queue):
        self.started.append({"arg": arg, "id": id, "task_queue": task_queue})


@pytest.mark.asyncio
async def test_temporal_orchestrator_serializes_source_to_strings():
    client = FakeClient()
    orch = TemporalRGroupDecompositionOrchestrator(client)
    run_id, ws = uuid.uuid4(), uuid.uuid4()
    mids = [uuid.uuid4(), uuid.uuid4()]
    await orch.schedule(run_id=run_id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=mids)
    started = client.started[0]
    assert started["id"] == f"rgroup-decomposition-{run_id}"
    assert started["arg"].run_id == str(run_id)
    assert started["arg"].workspace_id == str(ws)
    assert started["arg"].collection_id is None
    assert started["arg"].molecule_ids == [str(m) for m in mids]
