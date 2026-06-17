"""Unit tests for GetUmapClusterJob."""

import pytest
from uuid import uuid4

from returns.result import Failure, Success

from cellar.application.sar_analysis.get_umap_cluster_job import (
    GetUmapClusterJob,
    GetUmapClusterJobInput,
)
from cellar.domain.shared.errors import NotFoundError


class _Repo:
    def __init__(self, job=None):
        self.job = job
        self.calls: list[tuple] = []

    async def find_by_id_in_workspace(self, workspace_id, job_id):
        self.calls.append((job_id, workspace_id))
        if self.job is None:
            return None
        if self.job.workspace_id != workspace_id:
            return None
        return self.job


class _UoW:
    """Minimal async context manager stub — does not touch a DB."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_returns_failure_when_missing():
    repo = _Repo()
    result = await GetUmapClusterJob(repository=repo, uow=_UoW()).execute(
        GetUmapClusterJobInput(job_id=uuid4(), workspace_id=uuid4())
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_returns_success_when_found_in_same_workspace():
    from datetime import datetime, timezone
    from cellar.domain.sar_analysis.umap_job import UmapJob

    workspace_id = uuid4()
    job = UmapJob.create(
        workspace_id=workspace_id,
        requested_by=uuid4(),
        ids_hash="abc",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=datetime.now(timezone.utc),
    )
    result = await GetUmapClusterJob(repository=_Repo(job), uow=_UoW()).execute(
        GetUmapClusterJobInput(job_id=job.id, workspace_id=workspace_id)
    )
    assert isinstance(result, Success)
    assert result.unwrap() is job


@pytest.mark.asyncio
async def test_isolates_across_workspaces():
    """A job in workspace A must not be readable from workspace B."""
    from datetime import datetime, timezone
    from cellar.domain.sar_analysis.umap_job import UmapJob

    job = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="abc",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=datetime.now(timezone.utc),
    )
    other_workspace = uuid4()
    result = await GetUmapClusterJob(repository=_Repo(job), uow=_UoW()).execute(
        GetUmapClusterJobInput(job_id=job.id, workspace_id=other_workspace)
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
