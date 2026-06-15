"""Integration tests for SQLAlchemySarActivityProjectionRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _ready(ws, *, mh="m", ch="ch", value_count=0) -> SarActivityProjection:
    return (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash=mh,
            channel_hash=ch, channel_spec={"column": "drc:x"}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=value_count, now=_NOW)
    )


@pytest.mark.asyncio
async def test_save_and_find_by_id_scoped_to_workspace(uow):
    ws = uuid.uuid4()
    proj = _ready(ws)
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        await repo.save(proj)
        await uow.commit()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        found = await repo.find_by_id(proj.id, workspace_id=ws)
        other = await repo.find_by_id(proj.id, workspace_id=uuid.uuid4())
    assert found is not None and found.status == SarActivityProjectionStatus.READY
    assert other is None  # cross-workspace invisible


@pytest.mark.asyncio
async def test_find_cached_returns_latest_ready_for_keys(uow):
    ws = uuid.uuid4()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        await repo.save(_ready(ws, mh="m1", ch="c1", value_count=3))
        # Different channel hash -> not a hit for (m1, c1).
        await repo.save(_ready(ws, mh="m1", ch="OTHER"))
        await uow.commit()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        hit = await repo.find_cached(membership_hash="m1", channel_hash="c1")
        miss = await repo.find_cached(membership_hash="m1", channel_hash="nope")
    assert hit is not None and hit.value_count == 3
    assert miss is None


@pytest.mark.asyncio
async def test_write_values_and_count(uow):
    ws = uuid.uuid4()
    proj = _ready(ws)
    a, b = uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        await repo.save(proj)
        await repo.write_values(
            proj.id,
            [
                ActivityScalar(molecule_id=a, scalar=0.5, unit="uM", qualifier=None,
                               source="dose_response", snapshot={"value": 0.5}),
                ActivityScalar(molecule_id=b, scalar=2.0, unit="uM", qualifier=">",
                               source="dose_response", snapshot={"value": 2.0}),
            ],
        )
        await uow.commit()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        n = await repo.count_values(proj.id, workspace_id=ws)
    assert n == 2
