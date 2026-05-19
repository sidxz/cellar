"""Unit tests for CancelUmapClusterJob."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from returns.result import Failure, Success

from cellar.application.sar_analysis.cancel_umap_cluster_job import (
    CancelUmapClusterJob,
    CancelUmapClusterJobInput,
)
from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus
from cellar.domain.shared.errors import NotFoundError


class _Repo:
    def __init__(self, job):
        self.job = job
        self.saved = []
        self.calls: list[tuple] = []

    async def find_by_id(self, job_id, *, workspace_id):
        self.calls.append((job_id, workspace_id))
        if self.job is None:
            return None
        if self.job.workspace_id != workspace_id:
            return None
        return self.job

    async def save(self, j):
        self.saved.append(j)


class _Uow:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def commit(self):
        pass


class _Orch:
    def __init__(self):
        self.cancelled = []

    async def cancel(self, *, job_id):
        self.cancelled.append(job_id)


def _make_job(**kw):
    defaults = dict(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    return UmapJob.create(**defaults)


@pytest.mark.asyncio
async def test_cancels_pending_job():
    job = _make_job()
    repo = _Repo(job)
    orch = _Orch()
    result = await CancelUmapClusterJob(
        repository=repo, uow=_Uow(), orchestrator=orch
    ).execute(
        CancelUmapClusterJobInput(job_id=job.id, workspace_id=job.workspace_id)
    )
    assert isinstance(result, Success)
    assert repo.saved[0].status == UmapJobStatus.CANCELLED
    assert orch.cancelled == [job.id]


@pytest.mark.asyncio
async def test_returns_failure_when_job_missing():
    """The Result-based API surfaces NotFoundError so routes can return a 404."""
    repo = _Repo(None)
    orch = _Orch()
    result = await CancelUmapClusterJob(
        repository=repo, uow=_Uow(), orchestrator=orch
    ).execute(
        CancelUmapClusterJobInput(job_id=uuid4(), workspace_id=uuid4())
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
    assert repo.saved == []
    assert orch.cancelled == []


@pytest.mark.asyncio
async def test_noop_on_terminal_job():
    """Idempotent when the job is already in a terminal state — returns Success(job)."""
    job = _make_job()
    now = datetime.now(timezone.utc)
    terminal_job = job.mark_running(now).mark_ready(
        type("R", (), {"points": [], "picker_indices": []})(),
        now,
    )
    repo = _Repo(terminal_job)
    orch = _Orch()
    result = await CancelUmapClusterJob(
        repository=repo, uow=_Uow(), orchestrator=orch
    ).execute(
        CancelUmapClusterJobInput(
            job_id=terminal_job.id, workspace_id=terminal_job.workspace_id
        )
    )
    assert isinstance(result, Success)
    assert repo.saved == []
    assert orch.cancelled == []


@pytest.mark.asyncio
async def test_isolates_across_workspaces():
    """A cancel from workspace B must not touch a job owned by workspace A."""
    job = _make_job()
    repo = _Repo(job)
    orch = _Orch()
    result = await CancelUmapClusterJob(
        repository=repo, uow=_Uow(), orchestrator=orch
    ).execute(
        CancelUmapClusterJobInput(job_id=job.id, workspace_id=uuid4())
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
    assert repo.saved == []
    assert orch.cancelled == []
