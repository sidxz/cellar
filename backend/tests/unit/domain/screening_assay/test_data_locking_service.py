"""Tests for ``DataLockingService``."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.domain.screening_assay.data_locking_service import DataLockingService
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError


def _make_run(status: RunStatus = RunStatus.COMPLETED) -> Run:
    run = Run.create(
        workspace_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 5, 1),
        operator=uuid.uuid4(),
    )
    run.status = status
    return run


class TestDataLockingService:
    async def test_lock_completed_run_succeeds(self) -> None:
        run = _make_run(status=RunStatus.COMPLETED)
        actor = uuid.uuid4()

        svc = DataLockingService()
        result = await svc.lock_run(run, locked_by=actor, reason="regulatory hold")

        assert result is run
        assert run.is_locked is True
        assert run.locked_by == actor
        assert run.lock_reason == "regulatory hold"
        assert run.locked_at is not None

    async def test_lock_approved_run_succeeds(self) -> None:
        run = _make_run(status=RunStatus.APPROVED)

        svc = DataLockingService()
        result = await svc.lock_run(run, locked_by=uuid.uuid4(), reason="audit freeze")

        assert result is run
        assert run.is_locked is True

    async def test_lock_in_progress_run_raises_conflict(self) -> None:
        run = _make_run(status=RunStatus.IN_PROGRESS)

        svc = DataLockingService()
        with pytest.raises(ConflictError):
            await svc.lock_run(run, locked_by=uuid.uuid4(), reason="too early")

        assert run.is_locked is False

    async def test_unlock_locked_run_clears_lock_state(self) -> None:
        run = _make_run(status=RunStatus.COMPLETED)
        run.lock(locked_by=uuid.uuid4(), reason="hold")

        svc = DataLockingService()
        result = await svc.unlock_run(run, unlocked_by=uuid.uuid4(), reason="cleared")

        assert result is run
        assert run.is_locked is False
        assert run.locked_by is None
        assert run.lock_reason is None
        assert run.locked_at is None

    async def test_unlock_unlocked_run_raises_conflict(self) -> None:
        run = _make_run(status=RunStatus.COMPLETED)

        svc = DataLockingService()
        with pytest.raises(ConflictError):
            await svc.unlock_run(run, unlocked_by=uuid.uuid4(), reason="noop")
