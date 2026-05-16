from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Success

from cellar.application.export.list_exports import ListExports, ListExportsQuery
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
        format=ExportFormat.SDF,
        query_snapshot={},
        filename="out.sdf",
    )
    job.status = status
    return job


@pytest.mark.asyncio
async def test_list_returns_views_for_all_jobs():
    workspace = uuid.uuid4()
    jobs = [_job(workspace), _job(workspace, ExportStatus.READY)]
    repo = MagicMock()
    repo.list_in_workspace = AsyncMock(return_value=jobs)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = ListExports(_make_uow(), repo)
    result = await uc(ListExportsQuery(workspace_id=workspace), auth=auth)

    assert isinstance(result, Success)
    views = result.unwrap()
    assert len(views) == 2


@pytest.mark.asyncio
async def test_list_sets_download_url_only_for_ready():
    workspace = uuid.uuid4()
    pending_job = _job(workspace, ExportStatus.PENDING)
    ready_job = _job(workspace, ExportStatus.READY)
    repo = MagicMock()
    repo.list_in_workspace = AsyncMock(return_value=[pending_job, ready_job])
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = ListExports(_make_uow(), repo)
    result = await uc(ListExportsQuery(workspace_id=workspace), auth=auth)

    views = result.unwrap()
    pending_view = next(v for v in views if v.id == pending_job.id)
    ready_view = next(v for v in views if v.id == ready_job.id)
    assert pending_view.download_url is None
    assert ready_view.download_url == f"/api/v1/exports/{ready_job.id}/download"


@pytest.mark.asyncio
async def test_list_passes_cursor_to_repo():
    from datetime import datetime, UTC

    workspace = uuid.uuid4()
    cursor = datetime.now(UTC)
    repo = MagicMock()
    repo.list_in_workspace = AsyncMock(return_value=[])
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = ListExports(_make_uow(), repo)
    await uc(
        ListExportsQuery(workspace_id=workspace, limit=10, cursor_requested_at=cursor),
        auth=auth,
    )

    repo.list_in_workspace.assert_awaited_once_with(
        workspace, limit=10, cursor_requested_at=cursor
    )
