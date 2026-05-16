from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.export.prepare_export_download import (
    ExportDownloadView,
    PrepareExportDownload,
    PrepareExportDownloadQuery,
)
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.domain.shared.errors import ConflictError, GoneError, NotFoundError, ValidationError


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


def _job(
    workspace_id: uuid.UUID,
    status: ExportStatus = ExportStatus.READY,
    file_key: str | None = "exports/workspace/out.csv",
    content_type: str | None = "text/csv",
    filename: str | None = "results.csv",
) -> ExportJob:
    job = ExportJob.create(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={},
        filename=filename or "export.csv",
    )
    job.status = status
    job.file_key = file_key
    job.content_type = content_type
    return job


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ready_job_returns_download_view():
    workspace = uuid.uuid4()
    job = _job(workspace, ExportStatus.READY, file_key="exports/abc/out.csv")
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = PrepareExportDownload(_make_uow(), repo)
    result = await uc(
        PrepareExportDownloadQuery(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Success)
    view: ExportDownloadView = result.unwrap()
    assert view.file_key == "exports/abc/out.csv"
    assert view.content_type == "text/csv"
    assert view.filename == "results.csv"


@pytest.mark.asyncio
async def test_ready_job_falls_back_to_format_media_type_and_extension():
    """When content_type and filename are None on the job, fall back to format defaults."""
    workspace = uuid.uuid4()
    job = _job(workspace, ExportStatus.READY, file_key="exports/abc/out.sdf")
    # Simulate a job where content_type and filename were never stored
    job.format = ExportFormat.SDF
    job.content_type = None
    job.filename = None
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = PrepareExportDownload(_make_uow(), repo)
    result = await uc(
        PrepareExportDownloadQuery(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Success)
    view = result.unwrap()
    assert view.content_type == "chemical/x-sdf"
    assert view.filename == "export.sdf"


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_job_returns_not_found():
    workspace = uuid.uuid4()
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=None)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = PrepareExportDownload(_make_uow(), repo)
    result = await uc(
        PrepareExportDownloadQuery(workspace_id=workspace, job_id=uuid.uuid4()),
        auth=auth,
    )

    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_expired_job_returns_gone_error():
    workspace = uuid.uuid4()
    job = _job(workspace, ExportStatus.EXPIRED, file_key=None)
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = PrepareExportDownload(_make_uow(), repo)
    result = await uc(
        PrepareExportDownloadQuery(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Failure)
    assert isinstance(result.failure(), GoneError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [ExportStatus.PENDING, ExportStatus.RUNNING, ExportStatus.FAILED, ExportStatus.CANCELLED],
)
async def test_non_ready_non_expired_job_returns_conflict(status: ExportStatus):
    workspace = uuid.uuid4()
    job = _job(workspace, status)
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = PrepareExportDownload(_make_uow(), repo)
    result = await uc(
        PrepareExportDownloadQuery(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Failure)
    err = result.failure()
    assert isinstance(err, ConflictError)
    assert str(status) in err.message


@pytest.mark.asyncio
async def test_ready_job_missing_file_key_returns_validation_error():
    workspace = uuid.uuid4()
    job = _job(workspace, ExportStatus.READY, file_key=None)
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = PrepareExportDownload(_make_uow(), repo)
    result = await uc(
        PrepareExportDownloadQuery(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)
