from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Success

from cellar.application.sar_analysis.decomposition_rows import (
    FetchDecompositionRows,
    FetchDecompositionRowsInput,
)
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection

_NOW = datetime(2026, 6, 16, tzinfo=UTC)
_WS = uuid.uuid4()


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRunRepo:
    def __init__(self, run):
        self._run = run

    async def find_by_id_in_workspace(self, workspace_id, rid):
        return self._run if self._run.id == rid and self._run.workspace_id == workspace_id else None


class FakeProjRepo:
    def __init__(self, proj):
        self._proj = proj

    async def find_by_id_in_workspace(self, workspace_id, pid):
        if self._proj.id == pid and self._proj.workspace_id == workspace_id:
            return self._proj
        return None


class SpyReader:
    def __init__(self):
        self.fetch_calls = 0
        self.count_calls = 0
        self.ref_calls = 0

    async def fetch_rows(self, run_id, *, workspace_id, offset, limit, sort, projection_id=None, filter=None):
        self.fetch_calls += 1
        return []

    async def count_rows(self, run_id, *, workspace_id, projection_id=None, filter=None):
        self.count_calls += 1
        return 42

    async def fetch_matched_ids(self, run_id, *, workspace_id, projection_id=None, filter=None):
        return []

    async def activity_reference(self, run_id, *, workspace_id, projection_id, filter=None):
        self.ref_calls += 1
        return 0.1


def _run():
    run = RGroupDecompositionRun.create(
        workspace_id=_WS, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    )
    run.mark_running(_NOW)
    run.mark_ready(rgroup_labels=["R1"], matched_count=1, unmatched_count=0, total_count=1, now=_NOW)
    return run


def _proj():
    proj = SarActivityProjection.create(
        workspace_id=_WS, requested_by=uuid.uuid4(), membership_hash="m",
        channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
    )
    proj.mark_running(_NOW)
    proj.mark_ready(value_count=0, now=_NOW)
    return proj


def _uc(reader, run, proj):
    return FetchDecompositionRows(
        repository=FakeRunRepo(run),
        projection_repository=FakeProjRepo(proj),
        reader=reader,
        uow=FakeUoW(),
    )


@pytest.mark.asyncio
async def test_first_block_computes_total_and_reference():
    run, proj = _run(), _proj()
    reader = SpyReader()
    out = await _uc(reader, run, proj).execute(
        FetchDecompositionRowsInput(
            run_id=run.id, workspace_id=_WS, offset=0, limit=100, sort=[], projection_id=proj.id
        )
    )
    assert isinstance(out, Success)
    res = out.unwrap()
    assert res.total == 42
    assert res.activity_reference == 0.1
    assert reader.count_calls == 1
    assert reader.ref_calls == 1


@pytest.mark.asyncio
async def test_later_block_skips_count_and_reference():
    # Scroll blocks (offset > 0) must not re-run the full-scan COUNT + MIN; the FE
    # caches the values from the first block. total/reference come back null.
    run, proj = _run(), _proj()
    reader = SpyReader()
    out = await _uc(reader, run, proj).execute(
        FetchDecompositionRowsInput(
            run_id=run.id, workspace_id=_WS, offset=100, limit=100, sort=[], projection_id=proj.id
        )
    )
    res = out.unwrap()
    assert res.total is None
    assert res.activity_reference is None
    assert reader.count_calls == 0
    assert reader.ref_calls == 0
    assert reader.fetch_calls == 1  # rows are still fetched for the block
