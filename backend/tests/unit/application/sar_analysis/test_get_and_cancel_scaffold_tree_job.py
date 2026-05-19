from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest
from returns.result import Failure, Success

from cellar.application.sar_analysis.get_scaffold_tree_job import (
    GetScaffoldTreeJob,
    GetScaffoldTreeJobInput,
)
from cellar.application.sar_analysis.cancel_scaffold_tree_job import (
    CancelScaffoldTreeJob,
    CancelScaffoldTreeJobInput,
)
from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)
from cellar.domain.shared.errors import NotFoundError


class _NullUoW:
    """No-op UoW for unit tests — fakes don't need real DB sessions."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def commit(self):
        return []

    async def rollback(self):
        pass

    @property
    def is_active(self):
        return True


class _InMemoryRepo:
    def __init__(self):
        self.saved = {}

    async def save(self, job):
        self.saved[job.id] = job

    async def find_by_id(self, jid, *, workspace_id):
        job = self.saved.get(jid)
        if job and job.workspace_id == workspace_id:
            return job
        return None

    async def find_cached(self, **kw):
        return None


class _StubOrchestrator:
    def __init__(self):
        self.cancels = []

    async def schedule(self, **kw):
        pass

    async def cancel(self, *, job_id):
        self.cancels.append(job_id)


@pytest.mark.asyncio
async def test_get_returns_success_when_present():
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id, requested_by=uuid.uuid4(),
        ids_hash="x", now=datetime.now(timezone.utc),
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    result = await GetScaffoldTreeJob(repository=repo, uow=_NullUoW()).execute(
        GetScaffoldTreeJobInput(job_id=job.id, workspace_id=workspace_id)
    )
    assert isinstance(result, Success)
    assert result.unwrap().id == job.id


@pytest.mark.asyncio
async def test_get_returns_failure_when_missing():
    result = await GetScaffoldTreeJob(repository=_InMemoryRepo(), uow=_NullUoW()).execute(
        GetScaffoldTreeJobInput(job_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_get_returns_failure_when_workspace_mismatch():
    workspace_id = uuid.uuid4()
    other_workspace = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id, requested_by=uuid.uuid4(),
        ids_hash="x", now=datetime.now(timezone.utc),
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    result = await GetScaffoldTreeJob(repository=repo, uow=_NullUoW()).execute(
        GetScaffoldTreeJobInput(job_id=job.id, workspace_id=other_workspace)
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_cancel_transitions_to_cancelled_and_calls_orchestrator():
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id, requested_by=uuid.uuid4(),
        ids_hash="x", now=datetime.now(timezone.utc),
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    orchestrator = _StubOrchestrator()
    result = await CancelScaffoldTreeJob(
        repository=repo, orchestrator=orchestrator, uow=_NullUoW()
    ).execute(
        CancelScaffoldTreeJobInput(
            job_id=job.id, workspace_id=workspace_id,
            now=datetime.now(timezone.utc),
        )
    )
    assert isinstance(result, Success)
    assert result.unwrap().status == ScaffoldTreeJobStatus.CANCELLED
    assert orchestrator.cancels == [job.id]


@pytest.mark.asyncio
async def test_cancel_idempotent_on_terminal_returns_unchanged():
    workspace_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    job = (
        ScaffoldTreeJob.create(
            workspace_id=workspace_id, requested_by=uuid.uuid4(),
            ids_hash="x", now=now,
        )
        .mark_running(now)
        .mark_failed("boom", now)
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    result = await CancelScaffoldTreeJob(
        repository=repo, orchestrator=_StubOrchestrator(), uow=_NullUoW()
    ).execute(
        CancelScaffoldTreeJobInput(
            job_id=job.id, workspace_id=workspace_id, now=now,
        )
    )
    assert isinstance(result, Success)
    assert result.unwrap().status == ScaffoldTreeJobStatus.FAILED  # unchanged


@pytest.mark.asyncio
async def test_cancel_returns_failure_when_missing():
    result = await CancelScaffoldTreeJob(
        repository=_InMemoryRepo(), orchestrator=_StubOrchestrator(), uow=_NullUoW()
    ).execute(
        CancelScaffoldTreeJobInput(
            job_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
