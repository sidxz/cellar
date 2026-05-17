from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest

from cellar.application.sar_analysis.get_scaffold_tree_job import (
    GetScaffoldTreeJob,
    GetScaffoldTreeJobInput,
    ScaffoldTreeJobNotFound,
)
from cellar.application.sar_analysis.cancel_scaffold_tree_job import (
    CancelScaffoldTreeJob,
    CancelScaffoldTreeJobInput,
)
from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)


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
async def test_get_returns_job_when_present():
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id, requested_by=uuid.uuid4(),
        ids_hash="x", now=datetime.now(timezone.utc),
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    fetched = await GetScaffoldTreeJob(repository=repo).execute(
        GetScaffoldTreeJobInput(job_id=job.id, workspace_id=workspace_id)
    )
    assert fetched.id == job.id


@pytest.mark.asyncio
async def test_get_raises_not_found_when_missing():
    with pytest.raises(ScaffoldTreeJobNotFound):
        await GetScaffoldTreeJob(repository=_InMemoryRepo()).execute(
            GetScaffoldTreeJobInput(
                job_id=uuid.uuid4(), workspace_id=uuid.uuid4()
            )
        )


@pytest.mark.asyncio
async def test_get_raises_not_found_when_workspace_mismatch():
    workspace_id = uuid.uuid4()
    other_workspace = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id, requested_by=uuid.uuid4(),
        ids_hash="x", now=datetime.now(timezone.utc),
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    with pytest.raises(ScaffoldTreeJobNotFound):
        await GetScaffoldTreeJob(repository=repo).execute(
            GetScaffoldTreeJobInput(job_id=job.id, workspace_id=other_workspace)
        )


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
    cancelled = await CancelScaffoldTreeJob(
        repository=repo, orchestrator=orchestrator
    ).execute(
        CancelScaffoldTreeJobInput(
            job_id=job.id, workspace_id=workspace_id,
            now=datetime.now(timezone.utc),
        )
    )
    assert cancelled.status == ScaffoldTreeJobStatus.CANCELLED
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
    out = await CancelScaffoldTreeJob(
        repository=repo, orchestrator=_StubOrchestrator()
    ).execute(
        CancelScaffoldTreeJobInput(
            job_id=job.id, workspace_id=workspace_id, now=now,
        )
    )
    assert out.status == ScaffoldTreeJobStatus.FAILED  # unchanged
