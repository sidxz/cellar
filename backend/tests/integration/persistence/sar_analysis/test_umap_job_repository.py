"""Integration tests for UmapJobRepository.

Round-trip save+find, plus the cache lookup (ids_hash + picker + picker_param_hash + ttl).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus
from cellar.domain.sar_analysis.umap_types import UmapResult
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.umap_job_repository import (
    SQLAlchemyUmapJobRepository,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _empty_result(picker: str = "maxmin") -> UmapResult:
    return UmapResult(
        points=[],
        clusters=[],
        representatives=[],
        cluster_count=0,
        picker=picker,
        picker_params={"n": 50} if picker == "maxmin" else {"threshold": 0.4},
    )


@pytest.mark.asyncio
async def test_round_trip(uow) -> None:
    workspace_id = uuid4()
    job = UmapJob.create(
        workspace_id=workspace_id,
        requested_by=uuid4(),
        ids_hash="abc",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        found = await repo.find_by_id(job.id, workspace_id=workspace_id)

    assert found is not None
    assert found.id == job.id
    assert found.status == UmapJobStatus.PENDING


@pytest.mark.asyncio
async def test_find_by_id_isolates_across_workspaces(uow) -> None:
    """Cross-workspace probe by job UUID must return None."""
    workspace_a = uuid4()
    workspace_b = uuid4()
    job = UmapJob.create(
        workspace_id=workspace_a,
        requested_by=uuid4(),
        ids_hash=f"iso-{uuid4().hex}",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        miss = await repo.find_by_id(job.id, workspace_id=workspace_b)

    assert miss is None


@pytest.mark.asyncio
async def test_find_cached_hits_ready_within_ttl(uow) -> None:
    now = _now()
    workspace_id = uuid4()
    job = (
        UmapJob.create(
            workspace_id=workspace_id,
            requested_by=uuid4(),
            ids_hash="X",
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="ph",
            now=now - timedelta(minutes=5),
        )
        .mark_running(now - timedelta(minutes=4))
        .mark_ready(_empty_result(), now - timedelta(minutes=3))
    )
    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        found = await repo.find_cached(
            workspace_id=workspace_id,
            ids_hash="X",
            picker="maxmin",
            picker_param_hash="ph",
            ttl_seconds=3600,
        )

    assert found is not None
    assert found.status == UmapJobStatus.READY


@pytest.mark.asyncio
async def test_find_cached_misses_on_different_picker(uow) -> None:
    now = _now()
    workspace_id = uuid4()
    job = (
        UmapJob.create(
            workspace_id=workspace_id,
            requested_by=uuid4(),
            ids_hash="X",
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="phA",
            now=now - timedelta(minutes=3),
        )
        .mark_running(now - timedelta(minutes=2))
        .mark_ready(_empty_result(), now - timedelta(minutes=1))
    )
    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        miss = await repo.find_cached(
            workspace_id=workspace_id,
            ids_hash="X",
            picker="butina",
            picker_param_hash="phA",
            ttl_seconds=3600,
        )

    assert miss is None


@pytest.mark.asyncio
async def test_find_cached_misses_past_ttl(uow) -> None:
    # Use a distinct ids_hash so this job cannot collide with the READY row
    # inserted by test_find_cached_hits_ready_within_ttl (which also uses
    # ids_hash="X", picker="maxmin", picker_param_hash="ph").  Both tests
    # commit to the same shared DB (the UoW does NOT roll back on success),
    # so hash collisions between tests cause spurious cache hits.
    unique_hash = f"ttl-test-{uuid4().hex}"
    workspace_id = uuid4()
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=workspace_id,
            requested_by=uuid4(),
            ids_hash=unique_hash,
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="ph",
            now=now - timedelta(hours=3),
        )
        .mark_running(now - timedelta(hours=2, minutes=59))
        .mark_ready(_empty_result(), now - timedelta(hours=2))
    )
    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        miss = await repo.find_cached(
            workspace_id=workspace_id,
            ids_hash=unique_hash,
            picker="maxmin",
            picker_param_hash="ph",
            ttl_seconds=3600,
        )

    assert miss is None


@pytest.mark.asyncio
async def test_find_cached_isolates_across_workspaces(uow) -> None:
    """Same ids_hash in different workspaces must NOT cross-pollinate."""
    workspace_a = uuid4()
    workspace_b = uuid4()
    shared_hash = f"shared-{uuid4().hex}"
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=workspace_a,
            requested_by=uuid4(),
            ids_hash=shared_hash,
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="ph",
            now=now - timedelta(minutes=5),
        )
        .mark_running(now - timedelta(minutes=4))
        .mark_ready(_empty_result(), now - timedelta(minutes=3))
    )
    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        await repo.save(job)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyUmapJobRepository(uow)
        miss = await repo.find_cached(
            workspace_id=workspace_b,
            ids_hash=shared_hash,
            picker="maxmin",
            picker_param_hash="ph",
            ttl_seconds=3600,
        )

    assert miss is None
