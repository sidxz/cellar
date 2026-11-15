from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.export.start_export import StartExport, StartExportCommand
from cellar.domain.export.enums import ExportFormat, ExportSource
from cellar.domain.export.events import ExportRequested


@dataclass
class _Auth:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    workspace_role: str = "viewer"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        order = ["viewer", "editor", "admin"]
        return order.index(self.workspace_role) >= order.index(minimum_role)


def _make_uow():
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    return uow


def _dispatcher():
    dispatcher = MagicMock()
    dispatcher.dispatch_all = AsyncMock()
    return dispatcher


@pytest.mark.asyncio
async def test_start_persists_job_and_starts_workflow():
    workspace = uuid.uuid4()
    user = uuid.uuid4()
    repo = MagicMock()
    repo.save = AsyncMock()
    orch = MagicMock()
    orch.start = AsyncMock(return_value="wf-1")
    auth = _Auth(workspace_id=workspace, user_id=user)
    uow = _make_uow()
    # A real UoW returns the tracked aggregate's events; mirror that for the saved job.
    uow.commit = AsyncMock(side_effect=lambda: repo.save.call_args.args[0].collect_events())
    dispatcher = _dispatcher()

    uc = StartExport(uow, repo, orch, dispatcher)
    result = await uc(
        StartExportCommand(
            workspace_id=workspace,
            requested_by=user,
            source=ExportSource.SEARCH,
            format=ExportFormat.CSV,
            payload={"query": {}},
        ),
        auth=auth,
    )

    assert isinstance(result, Success)
    assert result.unwrap().job_id is not None
    repo.save.assert_awaited_once()
    orch.start.assert_awaited_once()
    # The request itself is audited: ExportRequested, attributed to the requester.
    (events,) = dispatcher.dispatch_all.await_args.args
    assert [type(e) for e in events] == [ExportRequested]
    assert events[0].user_id == user
    assert events[0].format == "csv"


@pytest.mark.asyncio
async def test_start_rejects_unsupported_source():
    workspace = uuid.uuid4()
    auth = _Auth(workspace_id=workspace, user_id=uuid.uuid4())
    repo = MagicMock()
    repo.save = AsyncMock()
    orch = MagicMock()
    orch.start = AsyncMock()

    uc = StartExport(_make_uow(), repo, orch, _dispatcher())
    # Use a value not in ExportSource.SEARCH path — monkey-patch a fake source
    cmd = StartExportCommand(
        workspace_id=workspace,
        requested_by=auth.user_id,
        source="runs",  # type: ignore[arg-type]  # unsupported
        format=ExportFormat.CSV,
        payload={},
    )
    result = await uc(cmd, auth=auth)

    assert isinstance(result, Failure)
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_filename_uses_hint():
    workspace = uuid.uuid4()
    user = uuid.uuid4()
    repo = MagicMock()
    repo.save = AsyncMock()
    orch = MagicMock()
    orch.start = AsyncMock(return_value="wf-2")
    auth = _Auth(workspace_id=workspace, user_id=user)

    uc = StartExport(_make_uow(), repo, orch, _dispatcher())
    result = await uc(
        StartExportCommand(
            workspace_id=workspace,
            requested_by=user,
            source=ExportSource.SEARCH,
            format=ExportFormat.XLSX,
            payload={},
            filename_hint="my-report",
        ),
        auth=auth,
    )

    assert isinstance(result, Success)
    # The saved job should have the hinted filename + extension
    saved_job = repo.save.call_args[0][0]
    assert saved_job.filename == "my-report.xlsx"


@pytest.mark.asyncio
async def test_start_keeps_who_asked_for_the_file():
    workspace, user = uuid.uuid4(), uuid.uuid4()
    repo = MagicMock()
    repo.save = AsyncMock()
    orch = MagicMock()
    orch.start = AsyncMock(return_value="wf-1")
    uc = StartExport(_make_uow(), repo, orch, _dispatcher())
    await uc(
        StartExportCommand(
            workspace_id=workspace,
            requested_by=user,
            requested_by_email="ada@lab.org",
            source=ExportSource.SEARCH,
            format=ExportFormat.PDF,
            payload={"query": {}},
        ),
        auth=_Auth(workspace_id=workspace, user_id=user),
    )
    assert repo.save.await_args.args[0].requested_by_email == "ada@lab.org"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fmt", "payload", "refused"),
    [
        (ExportFormat.PDF, {"run_id": str(uuid.uuid4())}, None),
        (ExportFormat.XLSX, {}, "needs the run's id"),
        (ExportFormat.SDF, {"run_id": str(uuid.uuid4())}, "Excel, CSV or PDF"),
    ],
)
async def test_a_run_export_names_its_run_and_skips_sdf(fmt, payload, refused):
    workspace, user = uuid.uuid4(), uuid.uuid4()
    repo = MagicMock()
    repo.save = AsyncMock()
    orch = MagicMock()
    orch.start = AsyncMock(return_value="wf-1")
    result = await StartExport(_make_uow(), repo, orch, _dispatcher())(
        StartExportCommand(
            workspace_id=workspace,
            requested_by=user,
            source=ExportSource.RUN,
            format=fmt,
            payload=payload,
        ),
        auth=_Auth(workspace_id=workspace, user_id=user),
    )
    if refused is None:
        assert isinstance(result, Success)
    else:
        assert isinstance(result, Failure) and refused in str(result.failure())
