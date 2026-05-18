"""NullUmapClusterOrchestrator runs the workflow inline."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cellar.infrastructure.temporal.orchestrators.umap_cluster import (
    NullUmapClusterOrchestrator,
)


@pytest.mark.asyncio
async def test_null_orchestrator_calls_runner_inline(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_runner(**kwargs):
        calls.append(kwargs)

    orch = NullUmapClusterOrchestrator(runner=fake_runner)
    await orch.schedule(
        job_id=uuid4(),
        workspace_id=uuid4(),
        molecule_ids=[uuid4()],
        picker="maxmin",
        picker_params={"n": 5},
    )
    assert len(calls) == 1
    assert calls[0]["picker"] == "maxmin"
