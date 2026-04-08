"""Tests for DataLockGuard and DataLockingService."""

import uuid
from datetime import date

import pytest

from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.data_locking_service import DataLockingService
from chem_vault.domain.screening_assay.enums import RunStatus
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.errors import ConflictError, DataLockedError, DomainError, ValidationError


# ---------------------------------------------------------------------------
# FakeLockChecker — test double
# ---------------------------------------------------------------------------


class FakeLockChecker:
    """In-memory RunLockChecker for testing."""

    def __init__(self, locked_run_ids: set[uuid.UUID] | None = None) -> None:
        self._locked = locked_run_ids or set()

    async def is_locked(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool:
        return run_id in self._locked


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(*, status: RunStatus = RunStatus.DRAFT) -> Run:
    """Create a run at the given status."""
    run = Run.create(
        workspace_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_date=date(2025, 7, 1),
        operator=uuid.uuid4(),
    )
    if status == RunStatus.DRAFT:
        return run
    run.start()
    if status == RunStatus.IN_PROGRESS:
        return run
    run.complete(plate_count=1, data_point_count=96)
    if status == RunStatus.COMPLETED:
        return run
    if status == RunStatus.APPROVED:
        run.approve(approved_by=uuid.uuid4())
        return run
    if status == RunStatus.REJECTED:
        run.reject(rejected_by=uuid.uuid4(), reason="Bad data")
        return run
    return run


# ---------------------------------------------------------------------------
# TestDataLockGuard
# ---------------------------------------------------------------------------


class TestDataLockGuard:
    @pytest.mark.asyncio
    async def test_unlocked_allows_write(self) -> None:
        workspace_id = uuid.uuid4()
        run_id = uuid.uuid4()
        checker = FakeLockChecker(locked_run_ids=set())
        guard = DataLockGuard(lock_checker=checker)

        # Should not raise
        await guard.guard_write(workspace_id, run_id)

    @pytest.mark.asyncio
    async def test_locked_blocks_write(self) -> None:
        workspace_id = uuid.uuid4()
        run_id = uuid.uuid4()
        checker = FakeLockChecker(locked_run_ids={run_id})
        guard = DataLockGuard(lock_checker=checker)

        with pytest.raises(DataLockedError) as exc_info:
            await guard.guard_write(workspace_id, run_id)
        assert str(run_id) in exc_info.value.message


# ---------------------------------------------------------------------------
# TestDataLockingService
# ---------------------------------------------------------------------------


class TestDataLockingService:
    @pytest.mark.asyncio
    async def test_lock_completed_run(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.COMPLETED)
        locker = uuid.uuid4()

        locked_run = await service.lock_run(run, locked_by=locker, reason="Final")

        assert locked_run.is_locked is True
        assert locked_run.locked_by == locker
        assert locked_run.lock_reason == "Final"

    @pytest.mark.asyncio
    async def test_lock_approved_run(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.APPROVED)

        locked_run = await service.lock_run(
            run, locked_by=uuid.uuid4(), reason="Archived"
        )
        assert locked_run.is_locked is True

    @pytest.mark.asyncio
    async def test_lock_draft_fails(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.DRAFT)

        with pytest.raises(ConflictError):
            await service.lock_run(
                run, locked_by=uuid.uuid4(), reason="Nope"
            )

    @pytest.mark.asyncio
    async def test_lock_in_progress_fails(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.IN_PROGRESS)

        with pytest.raises(ConflictError):
            await service.lock_run(
                run, locked_by=uuid.uuid4(), reason="Nope"
            )

    @pytest.mark.asyncio
    async def test_unlock_locked_run(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.COMPLETED)
        run.lock(locked_by=uuid.uuid4(), reason="Locked")

        unlocker = uuid.uuid4()
        unlocked_run = await service.unlock_run(
            run, unlocked_by=unlocker, reason="Correction needed"
        )

        assert unlocked_run.is_locked is False

    @pytest.mark.asyncio
    async def test_unlock_unlocked_run_fails(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.COMPLETED)

        with pytest.raises(ConflictError):
            await service.unlock_run(
                run, unlocked_by=uuid.uuid4(), reason="Nope"
            )

    @pytest.mark.asyncio
    async def test_lock_empty_reason_fails(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.COMPLETED)

        with pytest.raises(DomainError):
            await service.lock_run(
                run, locked_by=uuid.uuid4(), reason=""
            )

    @pytest.mark.asyncio
    async def test_unlock_empty_reason_fails(self) -> None:
        service = DataLockingService()
        run = _make_run(status=RunStatus.COMPLETED)
        run.lock(locked_by=uuid.uuid4(), reason="Locked")

        with pytest.raises(DomainError):
            await service.unlock_run(
                run, unlocked_by=uuid.uuid4(), reason=""
            )
