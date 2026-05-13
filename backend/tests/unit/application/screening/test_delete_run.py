"""Unit tests for the DeleteRun use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.delete_run import DeleteRun, DeleteRunCommand
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError, NotFoundError
from cellar.domain.shared.events import DomainEvent


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


def _make_run(
    workspace_id: uuid.UUID,
    *,
    status: RunStatus = RunStatus.DRAFT,
    locked: bool = False,
) -> Run:
    return Run(
        workspace_id=workspace_id,
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 4, 20),
        operator=uuid.uuid4(),
        status=status,
        is_locked=locked,
    )


def _build_uc(run: Run | None) -> tuple[DeleteRun, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    run_repo.delete = AsyncMock()

    readout_repo = AsyncMock()
    readout_repo.delete_for_run = AsyncMock(return_value=0)

    curve_repo = AsyncMock()
    curve_repo.delete_by_run = AsyncMock()

    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()

    uc = DeleteRun(
        uow=FakeUoW(),
        run_repo=run_repo,
        readout_data_repo=readout_repo,
        curve_repo=curve_repo,
        dispatcher=dispatcher,
    )
    return uc, run_repo, readout_repo, curve_repo, dispatcher


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeleteRun:
    @pytest.mark.asyncio
    async def test_delete_draft_run_succeeds(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, status=RunStatus.DRAFT)
        uc, run_repo, readout_repo, curve_repo, _ = _build_uc(run)

        result = await uc(
            DeleteRunCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert result.unwrap() is None
        curve_repo.delete_by_run.assert_awaited_once_with(auth.workspace_id, run.id)
        readout_repo.delete_for_run.assert_awaited_once_with(auth.workspace_id, run.id)
        run_repo.delete.assert_awaited_once_with(auth.workspace_id, run.id)

    @pytest.mark.asyncio
    async def test_delete_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, run_repo, readout_repo, curve_repo, _ = _build_uc(None)

        result = await uc(
            DeleteRunCommand(workspace_id=auth.workspace_id, run_id=uuid.uuid4()),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        run_repo.delete.assert_not_awaited()
        readout_repo.delete_for_run.assert_not_awaited()
        curve_repo.delete_by_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_locked_run_blocked(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, status=RunStatus.DRAFT, locked=True)
        uc, run_repo, _, _, _ = _build_uc(run)

        result = await uc(
            DeleteRunCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        run_repo.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_completed_run_blocked(self) -> None:
        auth = FakeAuth()
        for status in (RunStatus.COMPLETED, RunStatus.APPROVED, RunStatus.REJECTED):
            run = _make_run(auth.workspace_id, status=status)
            uc, run_repo, _, _, _ = _build_uc(run)
            result = await uc(
                DeleteRunCommand(workspace_id=auth.workspace_id, run_id=run.id),
                auth=auth,
            )
            assert isinstance(result, Failure), f"status={status}"
            assert isinstance(result.failure(), ConflictError), f"status={status}"
            run_repo.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_in_progress_run_succeeds(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, status=RunStatus.IN_PROGRESS)
        uc, run_repo, readout_repo, curve_repo, _ = _build_uc(run)

        result = await uc(
            DeleteRunCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )

        assert isinstance(result, Success), result
        run_repo.delete.assert_awaited_once_with(auth.workspace_id, run.id)
        readout_repo.delete_for_run.assert_awaited_once_with(auth.workspace_id, run.id)
        curve_repo.delete_by_run.assert_awaited_once_with(auth.workspace_id, run.id)
