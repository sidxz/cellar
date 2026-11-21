"""Migration 115 counts a note that predates tracking as one version, even on a closed campaign.

The backfill runs between dropping migration 027's lock trigger and creating the
split ones, so a closed campaign's noted row takes its count instead of the lock
refusing the whole migration.
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (  # noqa: E501
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_M115 = Path(__file__).parents[2] / "alembic" / "versions" / "115_campaign_result_note_stamp.py"


@pytest.fixture
async def tx(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncConnection, async_sessionmaker]]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        yield conn, factory
        await outer.rollback()


def _m115():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(_M115.stem, _M115)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_migration_115_counts_existing_notes_on_a_closed_campaign(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    cid = uuid.uuid4()
    noted = CampaignResult(campaign_id=cid, molecule_id=uuid.uuid4(), notes="Old note")
    empty = CampaignResult(campaign_id=cid, molecule_id=uuid.uuid4())
    campaign = Campaign(
        id=cid,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name=f"m115-{cid.hex[:6]}",
        created_by=uuid.uuid4(),
        results=[noted, empty],
    )
    async with AsyncUnitOfWork(factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(campaign)
        await uow.commit()
    await conn.execute(
        sa.text("UPDATE campaign SET status = 'closed' WHERE id = :id"), {"id": cid}
    )

    m115 = _m115()

    def down_then_up(sync_conn):  # type: ignore[no-untyped-def]
        with Operations.context(MigrationContext.configure(sync_conn)):
            m115.downgrade()
            m115.upgrade()

    await conn.run_sync(down_then_up)

    rows = await conn.execute(
        sa.text("SELECT id, notes_version_count FROM campaign_result WHERE campaign_id = :c"),
        {"c": cid},
    )
    assert dict(rows.all()) == {noted.id: 1, empty.id: 0}
