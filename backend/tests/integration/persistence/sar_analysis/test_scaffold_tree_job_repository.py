"""Integration tests for SQLAlchemyScaffoldTreeJobRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest

from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (
    SQLAlchemyScaffoldTreeJobRepository,
)


@pytest.mark.asyncio
async def test_save_and_find_by_id(uow):
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        ids_hash="hash-1",
        now=datetime.now(timezone.utc),
    )
    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        fetched = await repo.find_by_id(job.id, workspace_id=workspace_id)

    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.status == ScaffoldTreeJobStatus.PENDING


@pytest.mark.asyncio
async def test_save_updates_status_and_result(uow):
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        ids_hash="hash-2",
        now=datetime.now(timezone.utc),
    )

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    running = job.mark_running(datetime.now(timezone.utc))

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(running)
        await uow.commit()

    result = ScaffoldTreeResult(
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=42, cache_hit=False),
    )
    ready = running.mark_ready(result, datetime.now(timezone.utc))

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        await repo.save(ready)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        fetched = await repo.find_by_id(job.id, workspace_id=workspace_id)

    assert fetched.status == ScaffoldTreeJobStatus.READY
    assert fetched.result is not None
    assert fetched.result.stats.elapsed_ms == 42


@pytest.mark.asyncio
async def test_find_cached_within_ttl_returns_result(uow):
    workspace_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    job = (
        ScaffoldTreeJob.create(
            workspace_id=workspace_id,
            requested_by=uuid.uuid4(),
            ids_hash="cache-key-A",
            now=now - timedelta(minutes=5),
        )
        .mark_running(now - timedelta(minutes=4))
        .mark_ready(
            ScaffoldTreeResult(
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
            ),
            now - timedelta(minutes=3),
        )
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
    job = (
        ScaffoldTreeJob.create(
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            ids_hash="cache-key-B",
            now=now - timedelta(hours=2),
        )
        .mark_running(now - timedelta(hours=2))
        .mark_ready(
            ScaffoldTreeResult(
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
            ),
            now - timedelta(hours=2),
        )
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
    job = (
        ScaffoldTreeJob.create(
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            ids_hash="cache-key-D",
            now=now - timedelta(days=30),
        )
        .mark_running(now - timedelta(days=30))
        .mark_ready(
            ScaffoldTreeResult(
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
            ),
            now - timedelta(days=30),
        )
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
        await repo.save(job)  # status = pending
        await uow.commit()

    async with uow:
        repo = SQLAlchemyScaffoldTreeJobRepository(uow)
        cached = await repo.find_cached(ids_hash="cache-key-C", ttl_seconds=3600)

    assert cached is None
