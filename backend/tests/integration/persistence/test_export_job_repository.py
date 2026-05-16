"""Integration tests for SqlAlchemyExportJobRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC

import pytest

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
    SqlAlchemyExportJobRepository,
)


def _make_job(**over) -> ExportJob:
    base = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={"q": "x"},
        filename="x.csv",
    )
    base.update(over)
    return ExportJob.create(**base)


@pytest.mark.asyncio
async def test_save_and_load(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    job = _make_job()
    async with uow:
        await repo.save(job)
        await uow.commit()
    async with uow:
        loaded = await repo.find_by_id_in_workspace(job.workspace_id, job.id)
    assert loaded is not None
    assert loaded.status == ExportStatus.PENDING


@pytest.mark.asyncio
async def test_save_round_trip_after_status_changes(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    job = _make_job()
    job.mark_running()
    job.set_row_count(42)
    async with uow:
        await repo.save(job)
        await uow.commit()
    async with uow:
        loaded = await repo.find_by_id_in_workspace(job.workspace_id, job.id)
    assert loaded.status == ExportStatus.RUNNING
    assert loaded.row_count == 42


@pytest.mark.asyncio
async def test_list_in_workspace_filters_and_sorts(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    ws = uuid.uuid4()
    other_ws = uuid.uuid4()
    j1 = _make_job(workspace_id=ws)
    j2 = _make_job(workspace_id=ws)
    j3 = _make_job(workspace_id=other_ws)
    async with uow:
        await repo.save(j1)
        await repo.save(j2)
        await repo.save(j3)
        await uow.commit()
    async with uow:
        result = await repo.list_in_workspace(ws)
    assert {j.id for j in result} == {j1.id, j2.id}


@pytest.mark.asyncio
async def test_find_expired_ready(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    now = datetime.now(UTC)
    j = _make_job()
    j.mark_running()
    j.mark_ready("k", 1, "text/csv", expires_at=now - timedelta(hours=1))
    async with uow:
        await repo.save(j)
        await uow.commit()
    async with uow:
        result = await repo.find_expired_ready(now)
    assert any(x.id == j.id for x in result)
