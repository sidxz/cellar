"""Integration tests for SQLAlchemyRGroupDecompositionRunRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.shared.errors import ConcurrencyConflictError
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
        cached = await repo.find_cached(workspace_id=ws, membership_hash="mh", core_hash="ch")
        other_ws = await repo.find_cached(
            workspace_id=uuid.uuid4(), membership_hash="mh", core_hash="ch"
        )

    assert cached is not None
    assert cached.id == run.id
    assert other_ws is None  # cache is workspace-scoped — no cross-tenant hit


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
        miss = await repo.find_cached(workspace_id=ws, membership_hash="mh2", core_hash="ch-B")

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
        cached = await repo.find_cached(workspace_id=ws, membership_hash="mh3", core_hash="ch3")

    assert cached is None


from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment


async def _persist_run(uow, *, workspace_id, membership_hash="mh-a", core_hash="ch-a"):
    run = RGroupDecompositionRun.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        membership_hash=membership_hash,
        core_smiles="c1ccccc1",
        core_hash=core_hash,
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()
    return run


@pytest.mark.asyncio
async def test_write_and_count_assignments(uow):
    ws = uuid.uuid4()
    run = await _persist_run(uow, workspace_id=ws)
    rows = [
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "F"}),
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "Cl"}),
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "Br"}),
    ]
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, rows)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        n = await repo.count_assignments(run.id, workspace_id=ws)

    assert n == 3


@pytest.mark.asyncio
async def test_fetch_assignments_paginates_stably(uow):
    ws = uuid.uuid4()
    run = await _persist_run(uow, workspace_id=ws, membership_hash="mh-b", core_hash="ch-b")
    rows = [
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": str(i)}) for i in range(5)
    ]
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, rows)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        page1 = await repo.fetch_assignments(run.id, workspace_id=ws, offset=0, limit=2)
        page2 = await repo.fetch_assignments(run.id, workspace_id=ws, offset=2, limit=2)
        page3 = await repo.fetch_assignments(run.id, workspace_id=ws, offset=4, limit=2)

    seen = [a.molecule_id for a in (*page1, *page2, *page3)]
    assert len(seen) == 5
    assert len(set(seen)) == 5  # no overlap across pages — stable ordering


@pytest.mark.asyncio
async def test_fetch_count_scoped_to_workspace(uow):
    ws = uuid.uuid4()
    run = await _persist_run(uow, workspace_id=ws, membership_hash="mh-c", core_hash="ch-c")
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(
            run.id, [RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "F"})]
        )
        await uow.commit()

    other_ws = uuid.uuid4()
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        n = await repo.count_assignments(run.id, workspace_id=other_ws)
        rows = await repo.fetch_assignments(run.id, workspace_id=other_ws, offset=0, limit=10)

    assert n == 0        # the run belongs to ws, not other_ws
    assert rows == []


@pytest.mark.asyncio
async def test_save_rejects_stale_version(uow):
    # The lost-cancel race: a runner holding a stale RUNNING aggregate must not
    # be able to overwrite a row a concurrent cancel already advanced.
    ws = uuid.uuid4()
    run = RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="msv",
        core_smiles="c1ccccc1", core_hash="csv", now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        stale = await repo.find_by_id(run.id, workspace_id=ws)  # v1
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        fresh = await repo.find_by_id(run.id, workspace_id=ws)
        await repo.save(fresh.mark_running(_NOW))  # row advances to v2
        await uow.commit()
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        with pytest.raises(ConcurrencyConflictError):
            await repo.save(stale.mark_cancelled(_NOW))  # still expects v1 -> reject


@pytest.mark.asyncio
async def test_delete_assignments_removes_rows(uow):
    # Idempotent re-run: a runner resets prior assignment rows before recomputing.
    ws = uuid.uuid4()
    run = await _persist_run(uow, workspace_id=ws, membership_hash="mh-del", core_hash="ch-del")
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(
            run.id,
            [
                RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "F"}),
                RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "Cl"}),
            ],
        )
        await uow.commit()
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.delete_assignments(run.id)
        await uow.commit()
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        n = await repo.count_assignments(run.id, workspace_id=ws)
    assert n == 0
