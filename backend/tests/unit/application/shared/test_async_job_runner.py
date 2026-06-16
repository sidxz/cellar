from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.shared.async_job_runner import (
    claim_job,
    finalize_if_still_running,
)
from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


class _FakeJob(AsyncJob):
    def __init__(self, *, result: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.result = result

    def mark_ready(self, *, result: str, now: datetime) -> None:
        self._enter_ready(now)
        self.result = result


class FakeUoW:
    def __init__(self) -> None:
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.commits += 1
        return []


class FakeJobRepo:
    def __init__(self, job: _FakeJob | None = None) -> None:
        self._by_id: dict[uuid.UUID, _FakeJob] = {}
        if job is not None:
            self._by_id[job.id] = job

    async def find_by_id_in_workspace(self, workspace_id, id):
        job = self._by_id.get(id)
        return job if job is not None and job.workspace_id == workspace_id else None

    async def save(self, job):
        self._by_id[job.id] = job


def _pending(ws: uuid.UUID) -> _FakeJob:
    return _FakeJob(workspace_id=ws, requested_by=uuid.uuid4(), requested_at=_NOW)


# --- claim_job ---


@pytest.mark.asyncio
async def test_claim_pending_marks_running_and_returns_true():
    ws = uuid.uuid4()
    job = _pending(ws)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=ws, now=_NOW, job_type="test_job"
    )
    assert proceed is True
    assert repo._by_id[job.id].status == AsyncJobStatus.RUNNING
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_claim_running_reclaims_without_write():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_running(_NOW)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=ws, now=_NOW, job_type="test_job"
    )
    assert proceed is True
    assert uow.commits == 0  # re-claim does not re-commit


@pytest.mark.asyncio
async def test_claim_terminal_returns_false():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_cancelled(_NOW)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=ws, now=_NOW, job_type="test_job"
    )
    assert proceed is False


@pytest.mark.asyncio
async def test_claim_missing_returns_false():
    ws = uuid.uuid4()
    repo, uow = FakeJobRepo(), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=uuid.uuid4(), workspace_id=ws, now=_NOW, job_type="test_job"
    )
    assert proceed is False


@pytest.mark.asyncio
async def test_claim_wrong_workspace_returns_false():
    ws = uuid.uuid4()
    job = _pending(ws)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=uuid.uuid4(), now=_NOW, job_type="test_job"
    )
    assert proceed is False


# --- finalize_if_still_running ---


@pytest.mark.asyncio
async def test_finalize_applies_ready_when_running():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_running(_NOW)
    repo, uow = FakeJobRepo(job), FakeUoW()
    async with uow:
        await finalize_if_still_running(
            repo,
            uow,
            job_id=job.id,
            workspace_id=ws,
            apply_ready=lambda j: j.mark_ready(result="done", now=_NOW),
            job_type="test_job",
        )
    saved = repo._by_id[job.id]
    assert saved.status == AsyncJobStatus.READY
    assert saved.result == "done"
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_finalize_skips_when_cancelled():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_running(_NOW)
    job.mark_cancelled(_NOW)  # a concurrent cancel won
    repo, uow = FakeJobRepo(job), FakeUoW()
    async with uow:
        await finalize_if_still_running(
            repo,
            uow,
            job_id=job.id,
            workspace_id=ws,
            apply_ready=lambda j: j.mark_ready(result="done", now=_NOW),
            job_type="test_job",
        )
    assert repo._by_id[job.id].status == AsyncJobStatus.CANCELLED
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_finalize_skips_when_missing():
    ws = uuid.uuid4()
    repo, uow = FakeJobRepo(), FakeUoW()
    async with uow:
        await finalize_if_still_running(
            repo,
            uow,
            job_id=uuid.uuid4(),
            workspace_id=ws,
            apply_ready=lambda j: j.mark_ready(result="done", now=_NOW),
            job_type="test_job",
        )
    assert uow.commits == 0
