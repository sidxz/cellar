from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.purge_expired_exports import PurgeExpiredExports
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob


def _make_uow():
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    return uow


def _ready_job(workspace_id: uuid.UUID, file_key: str = "exports/x.csv") -> ExportJob:
    """Build an ExportJob in READY state with a file_key."""
    job = ExportJob(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={},
        filename="out.csv",
        status=ExportStatus.READY,
        file_key=file_key,
        byte_size=100,
        content_type="text/csv",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    return job


@pytest.mark.asyncio
async def test_purge_deletes_file_and_marks_expired():
    workspace = uuid.uuid4()
    job = _ready_job(workspace)

    repo = MagicMock()
    repo.find_expired_ready = AsyncMock(return_value=[job])
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()

    storage = MagicMock()
    storage.delete = AsyncMock()

    original_file_key = job.file_key
    uc = PurgeExpiredExports(_make_uow(), repo, storage)
    count = await uc()

    assert count == 1
    storage.delete.assert_awaited_once_with(original_file_key)
    assert job.status == ExportStatus.EXPIRED


@pytest.mark.asyncio
async def test_purge_tolerates_missing_file():
    workspace = uuid.uuid4()
    job = _ready_job(workspace, file_key="exports/gone.csv")

    repo = MagicMock()
    repo.find_expired_ready = AsyncMock(return_value=[job])
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()

    storage = MagicMock()
    storage.delete = AsyncMock(side_effect=FileNotFoundError)

    uc = PurgeExpiredExports(_make_uow(), repo, storage)
    count = await uc()

    # Should still mark the job expired even though file was already gone
    assert count == 1
    assert job.status == ExportStatus.EXPIRED


@pytest.mark.asyncio
async def test_purge_skips_job_deleted_between_list_and_fetch():
    workspace = uuid.uuid4()
    job = _ready_job(workspace)

    repo = MagicMock()
    repo.find_expired_ready = AsyncMock(return_value=[job])
    # Re-fetch returns None — job was concurrently deleted
    repo.find_by_id_in_workspace = AsyncMock(return_value=None)
    repo.save = AsyncMock()

    storage = MagicMock()
    storage.delete = AsyncMock()

    uc = PurgeExpiredExports(_make_uow(), repo, storage)
    count = await uc()

    assert count == 0
    repo.save.assert_not_awaited()
