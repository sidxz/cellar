from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.export.cancel_export import CancelExport, CancelExportCommand
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


def _job(workspace_id: uuid.UUID) -> ExportJob:
    return ExportJob.create(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={},
        filename="out.csv",
    )


@pytest.mark.asyncio
async def test_cancel_transitions_job_and_signals_workflow():
    workspace = uuid.uuid4()
    job = _job(workspace)
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()
    orch = MagicMock()
    orch.request_cancel = AsyncMock()
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = CancelExport(_make_uow(), repo, orch)
    result = await uc(
        CancelExportCommand(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    assert isinstance(result, Success)
    assert job.status == ExportStatus.CANCEL_REQUESTED
    repo.save.assert_awaited_once()
    orch.request_cancel.assert_awaited_once_with(f"export-{job.id}")


@pytest.mark.asyncio
async def test_cancel_returns_not_found_for_missing_job():
    workspace = uuid.uuid4()
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=None)
    orch = MagicMock()
    orch.request_cancel = AsyncMock()
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = CancelExport(_make_uow(), repo, orch)
    result = await uc(
        CancelExportCommand(workspace_id=workspace, job_id=uuid.uuid4()),
        auth=auth,
    )

    assert isinstance(result, Failure)
    repo.save = AsyncMock()
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_succeeds_even_if_orchestrator_raises():
    workspace = uuid.uuid4()
    job = _job(workspace)
    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()
    orch = MagicMock()
    orch.request_cancel = AsyncMock(side_effect=RuntimeError("workflow gone"))
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())

    uc = CancelExport(_make_uow(), repo, orch)
    result = await uc(
        CancelExportCommand(workspace_id=workspace, job_id=job.id),
        auth=auth,
    )

    # Domain state was persisted; orchestrator failure is best-effort
    assert isinstance(result, Success)
    assert job.status == ExportStatus.CANCEL_REQUESTED
