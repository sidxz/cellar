"""StartUmapClusterJob — 3-path dispatch: cache hit / sync / async."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
)
from cellar.application.sar_analysis.start_umap_cluster_job import (
    StartUmapClusterJob,
    StartUmapClusterJobInput,
)
from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus
from cellar.domain.sar_analysis.umap_types import UmapResult


class _FakeRepo:
    def __init__(self) -> None:
        self.saved: list[UmapJob] = []
        self.cached: UmapJob | None = None
        self.partial: UmapJob | None = None

    async def save(self, job: UmapJob) -> None:
        self.saved.append(job)

    async def find_by_id(self, _id: UUID) -> UmapJob | None:
        return None

    async def find_cached(self, **_kwargs) -> UmapJob | None:
        return self.cached

    async def find_compatible_for_pick(self, **_kwargs) -> UmapJob | None:
        return self.partial


class _FakeUow:
    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *args: Any) -> None: ...

    async def commit(self) -> None: ...


class _FakeCompute:
    def __init__(self) -> None:
        self.calls: list[ComputeUmapClusterInput] = []
        self.pick_only_calls: list[dict[str, Any]] = []

    async def execute(self, payload: ComputeUmapClusterInput) -> UmapResult:
        self.calls.append(payload)
        return UmapResult(
            points=[],
            clusters=[],
            representatives=[],
            cluster_count=0,
            picker=payload.picker,
            picker_params=payload.picker_params,
        )

    async def pick_only(
        self,
        *,
        existing: UmapResult,
        picker: str,
        picker_params: dict[str, Any],
    ) -> UmapResult:
        self.pick_only_calls.append(
            {"existing": existing, "picker": picker, "picker_params": picker_params}
        )
        return UmapResult(
            points=existing.points,
            clusters=existing.clusters,
            representatives=[],
            cluster_count=existing.cluster_count,
            picker=picker,
            picker_params=picker_params,
        )


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.scheduled: list[dict[str, Any]] = []

    async def schedule(self, **kwargs: Any) -> None:
        self.scheduled.append(kwargs)

    async def cancel(self, *, job_id: UUID) -> None: ...


@pytest.mark.asyncio
async def test_cache_hit_returns_result_no_compute() -> None:
    repo = _FakeRepo()
    repo.cached = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=datetime.now(timezone.utc),
    ).mark_running(datetime.now(timezone.utc)).mark_ready(
        UmapResult([], [], [], 0, "maxmin", {"n": 50}),
        datetime.now(timezone.utc),
    )
    compute = _FakeCompute()
    use_case = StartUmapClusterJob(
        compute=compute,
        repository=repo,
        orchestrator=_FakeOrchestrator(),
        uow=_FakeUow(),
        sync_limit=500,
    )
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=[uuid4() for _ in range(10)],
            picker="maxmin",
            picker_params={"n": 50},
            workspace_id=uuid4(),
            requested_by=uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.result is not None
    assert out.job is None
    assert compute.calls == []


@pytest.mark.asyncio
async def test_sync_path_computes_and_persists_ready() -> None:
    repo = _FakeRepo()
    compute = _FakeCompute()
    use_case = StartUmapClusterJob(
        compute=compute,
        repository=repo,
        orchestrator=_FakeOrchestrator(),
        uow=_FakeUow(),
        sync_limit=500,
    )
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=[uuid4() for _ in range(50)],
            picker="maxmin",
            picker_params={"n": 10},
            workspace_id=uuid4(),
            requested_by=uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.result is not None
    assert out.job is None
    assert len(compute.calls) == 1
    # Persisted as READY for future cache hit.
    assert len(repo.saved) == 1
    assert repo.saved[0].status == UmapJobStatus.READY


@pytest.mark.asyncio
async def test_async_path_schedules_when_above_limit() -> None:
    repo = _FakeRepo()
    orch = _FakeOrchestrator()
    use_case = StartUmapClusterJob(
        compute=_FakeCompute(),
        repository=repo,
        orchestrator=orch,
        uow=_FakeUow(),
        sync_limit=500,
    )
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=[uuid4() for _ in range(800)],
            picker="butina",
            picker_params={"threshold": 0.4},
            workspace_id=uuid4(),
            requested_by=uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.result is None
    assert out.job is not None
    assert out.job.status == UmapJobStatus.PENDING
    assert len(orch.scheduled) == 1
    assert orch.scheduled[0]["picker"] == "butina"


@pytest.mark.asyncio
async def test_partial_cache_hit_runs_pick_only_skipping_full_compute() -> None:
    """Chemist scrubs N at the same threshold → reuse UMAP + clusters, only
    re-run the picker."""
    repo = _FakeRepo()
    repo.partial = (
        UmapJob.create(
            workspace_id=uuid4(),
            requested_by=uuid4(),
            ids_hash="h",
            picker="maxmin",
            picker_params={"n": 5, "threshold": 0.4},
            picker_param_hash="ph_prev",
            now=datetime.now(timezone.utc),
        )
        .mark_running(datetime.now(timezone.utc))
        .mark_ready(
            UmapResult(
                points=[],
                clusters=[],
                representatives=[],
                cluster_count=3,
                picker="maxmin",
                picker_params={"n": 5, "threshold": 0.4},
            ),
            datetime.now(timezone.utc),
        )
    )
    compute = _FakeCompute()
    use_case = StartUmapClusterJob(
        compute=compute,
        repository=repo,
        orchestrator=_FakeOrchestrator(),
        uow=_FakeUow(),
        sync_limit=500,
    )
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=[uuid4() for _ in range(30)],
            picker="maxmin",
            picker_params={"n": 10, "threshold": 0.4},
            workspace_id=uuid4(),
            requested_by=uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.result is not None
    assert out.job is None
    # Full compute path SHOULD NOT have been taken.
    assert compute.calls == []
    # pick_only IS what ran.
    assert len(compute.pick_only_calls) == 1
    assert compute.pick_only_calls[0]["picker_params"] == {"n": 10, "threshold": 0.4}
    # And the new READY job is persisted for next-time full-cache-hit.
    assert len(repo.saved) == 1
    assert repo.saved[0].status == UmapJobStatus.READY
