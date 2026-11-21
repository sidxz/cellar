"""Migration 114 strips min_z_prime from stored column QC filters."""

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
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (  # noqa: E501
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_M114 = Path(__file__).parents[2] / "alembic" / "versions" / "114_drop_column_min_z_prime.py"


@pytest.fixture
async def tx(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncConnection, async_sessionmaker]]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        yield conn, factory
        await outer.rollback()


async def test_migration_114_strips_min_z_prime(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    cid = uuid.uuid4()
    filters = [
        {"min_z_prime": 0.5},
        {"require_approved": True, "min_z_prime": 0.5},
        {"require_approved": False},
    ]
    channels = [
        CampaignChannel(
            campaign_id=cid,
            label=f"C{i}",
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=i,
            qc_filter=f,
        )
        for i, f in enumerate(filters)
    ]
    campaign = Campaign(
        id=cid,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name=f"m114-{cid.hex[:6]}",
        created_by=uuid.uuid4(),
        channels=channels,
    )
    async with AsyncUnitOfWork(factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(campaign)
        await uow.commit()

    spec = importlib.util.spec_from_file_location(_M114.stem, _M114)
    assert spec is not None and spec.loader is not None
    m114 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m114)

    def up(sync_conn):  # type: ignore[no-untyped-def]
        with Operations.context(MigrationContext.configure(sync_conn)):
            m114.upgrade()

    await conn.run_sync(up)
    rows = await conn.execute(
        sa.text("SELECT label, qc_filter FROM campaign_channel WHERE campaign_id = :c"),
        {"c": cid},
    )
    got = {label: qc for label, qc in rows}
    assert got == {"C0": None, "C1": {"require_approved": True}, "C2": None}
