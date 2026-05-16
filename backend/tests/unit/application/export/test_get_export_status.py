from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.export.get_export_status import (
    ExportStatusView,
    GetExportStatus,
    GetExportStatusQuery,
)
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob


@dataclass
class _Auth:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    workspace_role: str = "viewer"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        return True


def _make_uow():
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    return uow


def _job(workspace_id: uuid.UUID, status: ExportStatus = ExportStatus.PENDING) -> ExportJob:
    job = ExportJob.create(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={},
        filename="out.csv",
    )
    job.status = status
    return job


@pytest.mark.asyncio
async def test_get_status_returns_view_for_existing_job():
    workspace = uuid.uuid4()
    job = _job(workspace)
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = GetExportStatus(_make_uow(), repo)
    result = await uc(
        GetExportStatusQuery(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Success)
    view: ExportStatusView = result.unwrap()
    assert view.id == job.id
    assert view.status == ExportStatus.PENDING
    assert view.download_url is None  # not READY


@pytest.mark.asyncio
async def test_get_status_includes_download_url_when_ready():
    workspace = uuid.uuid4()
    job = _job(workspace, ExportStatus.READY)
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = GetExportStatus(_make_uow(), repo)
    result = await uc(
        GetExportStatusQuery(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Success)
    assert f"/api/v1/exports/{job.id}/download" == result.unwrap().download_url


@pytest.mark.asyncio
async def test_get_status_not_found():
    workspace = uuid.uuid4()
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=None)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = GetExportStatus(_make_uow(), repo)
    result = await uc(
        GetExportStatusQuery(workspace_id=workspace, job_id=uuid.uuid4()),
        auth=auth,
    )

    assert isinstance(result, Failure)
