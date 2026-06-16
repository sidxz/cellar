from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput
from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus
from cellar.domain.shared.errors import ConcurrencyConflictError

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


class _FakeJob(AsyncJob):
    pass


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeJobRepo:
    def __init__(self, job: _FakeJob | None = None, *, raise_on_save: bool = False) -> None:
        self._by_id: dict[uuid.UUID, _FakeJob] = {}
        if job is not None:
            self._by_id[job.id] = job
        self._raise_on_save = raise_on_save

    async def find_by_id_in_workspace(self, workspace_id, id):
        job = self._by_id.get(id)
        return job if job is not None and job.workspace_id == workspace_id else None

    async def save(self, job):
        if self._raise_on_save:
            raise ConcurrencyConflictError(entity_type="Job", entity_id=str(job.id))
        self._by_id[job.id] = job


def _running(ws: uuid.UUID) -> _FakeJob:
    job = _FakeJob(workspace_id=ws, requested_by=uuid.uuid4(), requested_at=_NOW)
    job.mark_running(_NOW)
    return job


def _make(repo) -> MarkJobFailed:
    return MarkJobFailed(repository=repo, uow=FakeUoW(), job_type="test_job")


@pytest.mark.asyncio
async def test_mark_failed_from_running():
    ws = uuid.uuid4()
    job = _running(ws)
    repo = FakeJobRepo(job)
    await _make(repo).execute(
        MarkJobFailedInput(job_id=job.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[job.id].status == AsyncJobStatus.FAILED
    assert repo._by_id[job.id].error_message == "boom"


@pytest.mark.asyncio
async def test_mark_failed_from_pending():
    # The inline Start path can fail a job before it ever runs
    # (PENDING -> FAILED is a valid transition).
    ws = uuid.uuid4()
    job = _FakeJob(workspace_id=ws, requested_by=uuid.uuid4(), requested_at=_NOW)
    repo = FakeJobRepo(job)
    await _make(repo).execute(
        MarkJobFailedInput(job_id=job.id, workspace_id=ws, error="start error", now=_NOW)
    )
    assert repo._by_id[job.id].status == AsyncJobStatus.FAILED
    assert repo._by_id[job.id].error_message == "start error"


@pytest.mark.asyncio
async def test_mark_failed_idempotent_on_terminal():
    # A cancel that won the race must NOT be flipped to FAILED.
    ws = uuid.uuid4()
    job = _running(ws)
    job.mark_cancelled(_NOW)
    repo = FakeJobRepo(job)
    await _make(repo).execute(
        MarkJobFailedInput(job_id=job.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[job.id].status == AsyncJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_mark_failed_missing_is_noop():
    ws = uuid.uuid4()
    repo = FakeJobRepo()
    await _make(repo).execute(
        MarkJobFailedInput(job_id=uuid.uuid4(), workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id == {}


@pytest.mark.asyncio
async def test_mark_failed_swallows_concurrency_conflict():
    # A concurrent cancel advanced the row between our read and save; the
    # ConcurrencyConflictError is swallowed (does not propagate).
    ws = uuid.uuid4()
    job = _running(ws)
    repo = FakeJobRepo(job, raise_on_save=True)
    await _make(repo).execute(
        MarkJobFailedInput(job_id=job.id, workspace_id=ws, error="boom", now=_NOW)
    )
