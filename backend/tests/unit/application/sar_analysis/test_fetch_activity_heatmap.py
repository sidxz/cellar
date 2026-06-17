from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Failure, Success

from cellar.application.sar_analysis.activity_heatmap import (
    FetchActivityHeatmap,
    FetchActivityHeatmapInput,
    HeatmapResult,
)
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.domain.shared.errors import ValidationError

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


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

    async def find_by_id_in_workspace(self, workspace_id, run_id):
        if self._run and self._run.id == run_id and self._run.workspace_id == workspace_id:
            return self._run
        return None


class FakeProjRepo:
    def __init__(self, proj):
        self._proj = proj

    async def find_by_id(self, pid, *, workspace_id):
        if self._proj and self._proj.id == pid and self._proj.workspace_id == workspace_id:
            return self._proj
        return None


class FakeReader:
    def __init__(self):
        self.calls = 0

    async def fetch_heatmap(self, run_id, *, workspace_id, projection_id, axis_y, axis_x, top_k=30):
        self.calls += 1
        return HeatmapResult(
            x_values=[], y_values=[], cells=[], y_total=0, x_total=0,
            truncated=False, activity_reference=None,
        )


def _ready_run(ws, labels):
    run = RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    )
    run.mark_running(_NOW)
    run.mark_ready(rgroup_labels=labels, matched_count=0, unmatched_count=0, total_count=0, now=_NOW)
    return run


def _ready_proj(ws):
    return (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=0, now=_NOW)
    )


def _uc(run, proj, reader):
    return FetchActivityHeatmap(
        run_repository=FakeRunRepo(run),
        projection_repository=FakeProjRepo(proj),
        reader=reader,
        uow=FakeUoW(),
    )


@pytest.mark.asyncio
async def test_rejects_axis_not_in_run_labels():
    # A stale/bogus axis must 422, not silently return an empty matrix that reads
    # as "no data". The reader is never even queried with the invalid axis.
    ws = uuid.uuid4()
    run = _ready_run(ws, ["R1", "R2"])
    proj = _ready_proj(ws)
    reader = FakeReader()
    res = await _uc(run, proj, reader).execute(
        FetchActivityHeatmapInput(
            run_id=run.id, projection_id=proj.id, workspace_id=ws, axis_y="R1", axis_x="R3"
        )
    )
    assert isinstance(res, Failure)
    assert isinstance(res.failure(), ValidationError)
    assert reader.calls == 0


@pytest.mark.asyncio
async def test_accepts_valid_axes():
    ws = uuid.uuid4()
    run = _ready_run(ws, ["R1", "R2"])
    proj = _ready_proj(ws)
    reader = FakeReader()
    res = await _uc(run, proj, reader).execute(
        FetchActivityHeatmapInput(
            run_id=run.id, projection_id=proj.id, workspace_id=ws, axis_y="R1", axis_x="R2"
        )
    )
    assert isinstance(res, Success)
    assert reader.calls == 1
