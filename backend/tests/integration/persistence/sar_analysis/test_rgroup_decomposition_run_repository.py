"""Integration tests for SQLAlchemyRGroupDecompositionRunRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (
    SQLAlchemyRGroupDecompositionRunRepository,
)

_NOW = datetime.now(timezone.utc)


def _ready_run(*, workspace_id, membership_hash, core_hash) -> RGroupDecompositionRun:
    return (
        RGroupDecompositionRun.create(
            workspace_id=workspace_id,
            requested_by=uuid.uuid4(),
            membership_hash=membership_hash,
            core_smiles="c1ccccc1",
            core_hash=core_hash,
            now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(
            rgroup_labels=["R1"], matched_count=2, unmatched_count=0, total_count=2, now=_NOW
        )
    )


@pytest.mark.asyncio
async def test_save_and_find_by_id(uow):
    ws = uuid.uuid4()
    run = RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="m1",
        core_smiles="c1ccccc1",
        core_hash="c1",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        fetched = await repo.find_by_id(run.id, workspace_id=ws)

    assert fetched is not None
    assert fetched.status == RGroupDecompositionRunStatus.PENDING
    assert fetched.membership_hash == "m1"


@pytest.mark.asyncio
async def test_save_updates_status_labels_counts(uow):
    ws = uuid.uuid4()
    run = RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="m2",
        core_smiles="c1ccccc1",
        core_hash="c2",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    ready = run.mark_running(_NOW).mark_ready(
        rgroup_labels=["R1", "R2"], matched_count=5, unmatched_count=1, total_count=6, now=_NOW
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(ready)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        fetched = await repo.find_by_id(run.id, workspace_id=ws)

    assert fetched.status == RGroupDecompositionRunStatus.READY
    assert fetched.rgroup_labels == ["R1", "R2"]
    assert fetched.matched_count == 5
    assert fetched.total_count == 6


@pytest.mark.asyncio
async def test_find_cached_returns_latest_ready_for_hash_pair(uow):
    ws = uuid.uuid4()
    run = _ready_run(workspace_id=ws, membership_hash="mh", core_hash="ch")
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        cached = await repo.find_cached(membership_hash="mh", core_hash="ch")

    assert cached is not None
    assert cached.id == run.id


@pytest.mark.asyncio
async def test_find_cached_misses_on_different_core(uow):
    ws = uuid.uuid4()
    run = _ready_run(workspace_id=ws, membership_hash="mh2", core_hash="ch-A")
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        miss = await repo.find_cached(membership_hash="mh2", core_hash="ch-B")

    assert miss is None  # version-aware membership / core change ⇒ cache miss


@pytest.mark.asyncio
async def test_find_cached_ignores_pending(uow):
    ws = uuid.uuid4()
    run = RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="mh3",
        core_smiles="c1ccccc1",
        core_hash="ch3",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        cached = await repo.find_cached(membership_hash="mh3", core_hash="ch3")

    assert cached is None
