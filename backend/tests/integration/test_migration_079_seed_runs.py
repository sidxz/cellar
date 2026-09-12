"""Integration test: migration 079 BACKFILL_SQL derives campaign.seed_runs.

For each campaign, the distinct ``RunRef`` run ids over its results' ``added_from``
joined to the run's protocol, as ``[{run_id, protocol_id}]`` ordered by run_date;
a RunRef whose run no longer exists contributes nothing; a campaign with no
run-attributed rows keeps ``[]``.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.source_ref import CollectionRef, RunRef, SeedRun
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_M079_PATH = Path(__file__).parents[2] / "alembic" / "versions" / "079_campaign_seed_runs.py"
_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


def _load_m079():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m079", _M079_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _insert_protocol(session, protocol_id: uuid.UUID, ws_id: uuid.UUID) -> None:  # type: ignore[no-untyped-def]
    await session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', "
            "false, 'uM', 'high', 1, 1, :user)"
        ),
        {"id": protocol_id, "ws": ws_id, "name": f"P-{str(protocol_id)[:8]}", "user": _USER_ID},
    )


async def _insert_run(  # type: ignore[no-untyped-def]
    session, run_id: uuid.UUID, protocol_id: uuid.UUID, ws_id: uuid.UUID, run_date: date
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, "
            "status, is_locked, version) "
            "VALUES (:id, :ws, :proto, :run_date, :user, 'draft', false, 1)"
        ),
        {"id": run_id, "ws": ws_id, "proto": protocol_id, "run_date": run_date, "user": _USER_ID},
    )


def _campaign(ws_id: uuid.UUID, *refs) -> Campaign:  # type: ignore[no-untyped-def]
    c = Campaign.create(
        workspace_id=ws_id,
        project_id=uuid.uuid4(),
        name=f"C-{uuid.uuid4().hex[:6]}",
        description=None,
        created_by=_USER_ID,
    )
    for ref in refs:
        c.add_result(CampaignResult(campaign_id=c.id, molecule_id=uuid.uuid4(), added_from=ref))
    return c


@pytest.mark.asyncio
async def test_backfill_derives_seed_runs_from_run_refs(session_factory) -> None:  # type: ignore[no-untyped-def]
    m079 = _load_m079()
    ws_id = uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    run_a, run_b, run_c, run_gone = (uuid.uuid4() for _ in range(4))

    async with session_factory() as session, session.begin():
        await _insert_protocol(session, p1, ws_id)
        await _insert_protocol(session, p2, ws_id)
        await _insert_run(session, run_b, p1, ws_id, date(2026, 3, 1))
        await _insert_run(session, run_a, p1, ws_id, date(2026, 1, 1))
        await _insert_run(session, run_c, p2, ws_id, date(2026, 2, 1))

    seeded = _campaign(
        ws_id,
        RunRef(run_id=run_b),
        RunRef(run_id=run_a),
        RunRef(run_id=run_b),  # repeated run → one seed entry
        RunRef(run_id=run_c),
        RunRef(run_id=run_gone),  # run row missing → dropped
        CollectionRef(collection_id=uuid.uuid4()),
    )
    unseeded = _campaign(ws_id, CollectionRef(collection_id=uuid.uuid4()))
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(seeded)
        await repo.save(unseeded)
        await uow.commit()

    async with session_factory() as session, session.begin():
        await session.execute(sa.text(m079.BACKFILL_SQL))

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        seeded_after = await repo.find_by_id(seeded.id)
        unseeded_after = await repo.find_by_id(unseeded.id)
    assert seeded_after is not None and unseeded_after is not None
    # Ordered by run_date: a (Jan, P1), c (Feb, P2), b (Mar, P1).
    assert seeded_after.seed_runs == [SeedRun(run_a, p1), SeedRun(run_c, p2), SeedRun(run_b, p1)]
    assert seeded_after.seed_run_ids_for(p1) == [run_a, run_b]
    assert unseeded_after.seed_runs == []
