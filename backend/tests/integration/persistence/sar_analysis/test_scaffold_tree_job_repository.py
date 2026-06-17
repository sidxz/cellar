"""Integration tests for SQLAlchemyScaffoldTreeJobRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.domain.shared.errors import ConcurrencyConflictError
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (
    SQLAlchemyScaffoldTreeJobRepository,
)

_NOW = datetime.now(timezone.utc)


def _minimal_result() -> ScaffoldTreeResult:
    return ScaffoldTreeResult(
        nodes=[],
        edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=42, cache_hit=False),
    )


@pytest.mark.asyncio
async def test_save_and_find_by_id(uow):
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        ids_hash="hash-1",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        fetched = await repo.find_by_id_in_workspace(workspace_id, job.id)

    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.status == AsyncJobStatus.PENDING


@pytest.mark.asyncio
async def test_save_updates_status_and_result(uow):
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        ids_hash="hash-2",
        now=_NOW,
    )

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    job.mark_running(_NOW)

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    result = _minimal_result()
    job.mark_ready(result=result, now=_NOW)

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        fetched = await repo.find_by_id_in_workspace(workspace_id, job.id)

    assert fetched.status == AsyncJobStatus.READY
    assert fetched.result is not None
    assert fetched.result.stats.elapsed_ms == 42


@pytest.mark.asyncio
async def test_find_cached_within_ttl_returns_result(uow):
    workspace_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        ids_hash="cache-key-A",
        now=now - timedelta(minutes=5),
    )
    job.mark_running(now - timedelta(minutes=4))
    job.mark_ready(
        result=ScaffoldTreeResult(
            stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
        ),
        now=now - timedelta(minutes=3),
    )

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        cached = await repo.find_cached(ids_hash="cache-key-A", ttl_seconds=3600)

    assert cached is not None
    assert cached.stats.elapsed_ms == 10


@pytest.mark.asyncio
async def test_find_cached_beyond_ttl_returns_none(uow):
    now = datetime.now(timezone.utc)
    job = ScaffoldTreeJob.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        ids_hash="cache-key-B",
        now=now - timedelta(hours=2),
    )
    job.mark_running(now - timedelta(hours=2))
    job.mark_ready(
        result=ScaffoldTreeResult(
            stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
        ),
        now=now - timedelta(hours=2),
    )

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        cached = await repo.find_cached(ids_hash="cache-key-B", ttl_seconds=3600)

    assert cached is None


@pytest.mark.asyncio
async def test_find_cached_with_none_ttl_returns_old_ready_result(uow):
    """ttl_seconds=None → id-based cache: a ready tree never expires on time."""
    now = datetime.now(timezone.utc)
    job = ScaffoldTreeJob.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        ids_hash="cache-key-D",
        now=now - timedelta(days=30),
    )
    job.mark_running(now - timedelta(days=30))
    job.mark_ready(
        result=ScaffoldTreeResult(
            stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
        ),
        now=now - timedelta(days=30),
    )

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        cached = await repo.find_cached(ids_hash="cache-key-D", ttl_seconds=None)

    # 30 days old — would miss any finite TTL, but None means no time expiry.
    assert cached is not None


@pytest.mark.asyncio
async def test_find_cached_ignores_non_ready_jobs(uow):
    job = ScaffoldTreeJob.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        ids_hash="cache-key-C",
        now=datetime.now(timezone.utc),
    )

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)  # status = PENDING
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        cached = await repo.find_cached(ids_hash="cache-key-C", ttl_seconds=3600)

    assert cached is None


@pytest.mark.asyncio
async def test_save_rejects_stale_version(uow):
    # The lost-cancel race: a runner holding a stale RUNNING aggregate must not
    # be able to overwrite a row a concurrent cancel already advanced.
    ws = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        ids_hash="hash-sv",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    # Capture a stale reference (v1) before advancing
    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        stale = await repo.find_by_id_in_workspace(ws, job.id)  # v1

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        fresh = await repo.find_by_id_in_workspace(ws, job.id)
        fresh.mark_running(_NOW)  # row advances to v2
        await repo.save(fresh)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        with pytest.raises(ConcurrencyConflictError):
            stale.mark_cancelled(_NOW)  # still expects v1 -> reject
            await repo.save(stale)
