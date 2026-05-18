"""Unit tests for CancelUmapClusterJob."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus


class _Repo:
    def __init__(self, job):
        self.job = job
        self.saved = []

    async def find_by_id(self, _):
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
    await CancelUmapClusterJob(repository=repo, uow=_Uow(), orchestrator=orch).execute(job.id)
    assert repo.saved[0].status == UmapJobStatus.CANCELLED
    assert orch.cancelled == [job.id]


@pytest.mark.asyncio
async def test_noop_when_job_missing():
    """Returns silently when the job does not exist."""
    repo = _Repo(None)
    orch = _Orch()
    # Should not raise.
    await CancelUmapClusterJob(repository=repo, uow=_Uow(), orchestrator=orch).execute(uuid4())
    assert repo.saved == []
    assert orch.cancelled == []


@pytest.mark.asyncio
async def test_noop_on_terminal_job():
    """Idempotent when the job is already in a terminal state."""
    job = _make_job()
    now = datetime.now(timezone.utc)
    terminal_job = job.mark_running(now).mark_ready(
        # UmapResult minimal stub
        type("R", (), {"points": [], "picker_indices": []})(),
        now,
    )
    repo = _Repo(terminal_job)
    orch = _Orch()
    # Should not raise; terminal transition is swallowed.
    await CancelUmapClusterJob(repository=repo, uow=_Uow(), orchestrator=orch).execute(terminal_job.id)
    assert repo.saved == []
    assert orch.cancelled == []
