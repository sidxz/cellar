"""Unit tests for NullScaffoldTreeOrchestrator.

Verifies that the Null path (used when TEMPORAL_DISABLED=1 or in tests)
fires the runner as a fire-and-forget asyncio.Task and that cancel() is a
no-op — mirroring the NullExportOrchestrator behaviour exactly.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.scaffold_tree import (
    NullScaffoldTreeOrchestrator,
)


class _SpyRunner:
    def __init__(self):
        self.called_with = None

    async def run(self, *, job_id, workspace_id, molecule_ids):
        self.called_with = (job_id, workspace_id, list(molecule_ids))


@pytest.mark.asyncio
async def test_null_orchestrator_invokes_runner_inline():
    runner = _SpyRunner()
    o = NullScaffoldTreeOrchestrator(runner=runner)
    job_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    mol_ids = [uuid.uuid4(), uuid.uuid4()]
    await o.schedule(job_id=job_id, workspace_id=workspace_id, molecule_ids=mol_ids)
    await asyncio.sleep(0.05)  # NullOrchestrator is fire-and-forget
    assert runner.called_with == (job_id, workspace_id, mol_ids)


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    o = NullScaffoldTreeOrchestrator(runner=_SpyRunner())
    await o.cancel(job_id=uuid.uuid4())  # no exception expected


@pytest.mark.asyncio
async def test_null_orchestrator_passes_workspace_id_to_runner():
    """workspace_id is threaded through schedule → runner.run unchanged."""
    runner = _SpyRunner()
    o = NullScaffoldTreeOrchestrator(runner=runner)
    job_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    await o.schedule(job_id=job_id, workspace_id=workspace_id, molecule_ids=[])
    await asyncio.sleep(0.05)
    assert runner.called_with is not None
    assert runner.called_with[1] == workspace_id
