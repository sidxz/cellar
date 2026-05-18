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
async def test_round_trip(db_session) -> None:
    repo = SQLAlchemyUmapJobRepository(db_session)
    job = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="abc",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    await repo.save(job)
    await db_session.flush()
    found = await repo.find_by_id(job.id)
    assert found is not None
    assert found.id == job.id
    assert found.status == UmapJobStatus.PENDING


@pytest.mark.asyncio
async def test_find_cached_hits_ready_within_ttl(db_session) -> None:
    repo = SQLAlchemyUmapJobRepository(db_session)
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=uuid4(),
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
    await repo.save(job)
    await db_session.flush()
    found = await repo.find_cached(
        ids_hash="X", picker="maxmin", picker_param_hash="ph", ttl_seconds=3600
    )
    assert found is not None
    assert found.status == UmapJobStatus.READY


@pytest.mark.asyncio
async def test_find_cached_misses_on_different_picker(db_session) -> None:
    repo = SQLAlchemyUmapJobRepository(db_session)
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=uuid4(),
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
    await repo.save(job)
    await db_session.flush()
    miss = await repo.find_cached(
        ids_hash="X", picker="butina", picker_param_hash="phA", ttl_seconds=3600
    )
    assert miss is None


@pytest.mark.asyncio
async def test_find_cached_misses_past_ttl(db_session) -> None:
    repo = SQLAlchemyUmapJobRepository(db_session)
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=uuid4(),
            requested_by=uuid4(),
            ids_hash="X",
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="ph",
            now=now - timedelta(hours=3),
        )
        .mark_running(now - timedelta(hours=2, minutes=59))
        .mark_ready(_empty_result(), now - timedelta(hours=2))
    )
    await repo.save(job)
    await db_session.flush()
    miss = await repo.find_cached(
        ids_hash="X", picker="maxmin", picker_param_hash="ph", ttl_seconds=3600
    )
    assert miss is None
