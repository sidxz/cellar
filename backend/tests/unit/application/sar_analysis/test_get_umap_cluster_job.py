"""Unit tests for GetUmapClusterJob."""

import pytest
from uuid import uuid4

from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob


class _Repo:
    def __init__(self, job=None):
        self.job = job

    async def find_by_id(self, _id):
        return self.job


@pytest.mark.asyncio
async def test_returns_none_when_missing():
    out = await GetUmapClusterJob(_Repo()).execute(uuid4())
    assert out is None


@pytest.mark.asyncio
async def test_returns_job_when_found():
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
    out = await GetUmapClusterJob(_Repo(job)).execute(job.id)
    assert out is job
