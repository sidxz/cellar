from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest

from cellar.application.sar_analysis.start_scaffold_tree_job import (
    StartScaffoldTreeJob,
    StartScaffoldTreeJobInput,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)


class _NullUoW:
    """No-op UoW for unit tests — fakes don't need real DB sessions."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def commit(self):
        return []

    async def rollback(self):
        pass

    @property
    def is_active(self):
        return True


class _CacheHitBuilder:
    async def execute(self, payload):
        return ScaffoldTreeResult(
            nodes=[], edges=[],
            stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=True),
        )


class _CacheMissBuilder:
    async def execute(self, payload):
        return ScaffoldTreeResult(
            nodes=[], edges=[],
            stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
        )


class _InMemoryRepo:
    def __init__(self):
        self.saved = []

    async def save(self, job):
        self.saved.append(job)

    async def find_by_id_in_workspace(self, workspace_id, job_id):
        for j in self.saved:
            if j.id == job_id and j.workspace_id == workspace_id:
                return j
        return None

    async def find_cached(self, *, ids_hash, ttl_seconds):
        return None


class _StubOrchestrator:
    def __init__(self):
        self.scheduled = []

    async def schedule(self, *, job_id, workspace_id, molecule_ids):
        self.scheduled.append((job_id, workspace_id, list(molecule_ids)))

    async def cancel(self, *, job_id):
        pass


@pytest.mark.asyncio
async def test_cache_hit_returns_inline_no_job():
    out = await StartScaffoldTreeJob(
        builder=_CacheHitBuilder(),
        repository=_InMemoryRepo(),
        orchestrator=_StubOrchestrator(),
        uow=_NullUoW(),
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=[uuid.uuid4()],
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is not None
    assert out.job is None
    assert out.tree.stats.cache_hit is True


@pytest.mark.asyncio
async def test_small_set_runs_sync_no_job():
    repo = _InMemoryRepo()
    orchestrator = _StubOrchestrator()
    out = await StartScaffoldTreeJob(
        builder=_CacheMissBuilder(),
        repository=repo,
        orchestrator=orchestrator,
        uow=_NullUoW(),
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=[uuid.uuid4() for _ in range(5)],
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is not None
    assert out.job is None
    # The sync path persists a READY job so the result is cached for next time
    assert any(j.status.value == "ready" for j in repo.saved)
    assert orchestrator.scheduled == []


@pytest.mark.asyncio
async def test_large_set_creates_job_and_schedules():
    repo = _InMemoryRepo()
    orchestrator = _StubOrchestrator()
    molecule_ids = [uuid.uuid4() for _ in range(501)]
    out = await StartScaffoldTreeJob(
        builder=_CacheMissBuilder(),
        repository=repo,
        orchestrator=orchestrator,
        uow=_NullUoW(),
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=molecule_ids,
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is None
    assert out.job is not None
    assert out.job.status.value == "pending"
    assert orchestrator.scheduled and orchestrator.scheduled[0][0] == out.job.id
    assert orchestrator.scheduled[0][1] == out.job.workspace_id


@pytest.mark.asyncio
async def test_large_set_cache_hit_returns_inline_no_job():
    repo = _InMemoryRepo()

    class _CacheRepo:
        async def save(self, job):
            repo.saved.append(job)

        async def find_by_id_in_workspace(self, workspace_id, job_id):
            return None

        async def find_cached(self, *, ids_hash, ttl_seconds):
            return ScaffoldTreeResult(
                nodes=[], edges=[],
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=5, cache_hit=False),
            )

    orchestrator = _StubOrchestrator()
    out = await StartScaffoldTreeJob(
        builder=_CacheMissBuilder(),
        repository=_CacheRepo(),
        orchestrator=orchestrator,
        uow=_NullUoW(),
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=[uuid.uuid4() for _ in range(1000)],
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is not None
    assert out.job is None
    assert orchestrator.scheduled == []
