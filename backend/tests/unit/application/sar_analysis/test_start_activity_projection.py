from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.start_activity_projection import (
    StartActivityProjection,
    StartActivityProjectionInput,
)
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule

_NOW = datetime(2026, 6, 15, tzinfo=UTC)
_COLUMN = "drc:" + str(uuid.uuid4())


def _channel() -> ActivityChannelSpec:
    return ActivityChannelSpec(
        column=_COLUMN, source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    )


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRepo:
    def __init__(self, cached=None):
        self._by_id = {}
        self._cached = cached
        self.written = {}

    async def save(self, p):
        self._by_id[p.id] = p

    async def find_by_id(self, pid, *, workspace_id):
        return self._by_id.get(pid)

    async def find_cached(self, *, workspace_id, membership_hash, channel_hash):
        return self._cached

    async def write_values(self, pid, values):
        self.written.setdefault(pid, []).extend(values)


class FakeEnricher:
    def __init__(self, table):
        self._table = table

    async def enrich_molecules(self, ws, ids, cols, *, selection_rule, qualifier_handling, run_scopes=None):
        return {mid: self._table[mid] for mid in ids if mid in self._table}


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for b in self._batches:
            yield b


class FakeOrchestrator:
    def __init__(self):
        self.scheduled = []

    async def schedule(self, *, projection_id, workspace_id, channel_spec, collection_id=None, molecule_ids=None):
        self.scheduled.append(
            {"projection_id": projection_id, "collection_id": collection_id, "channel_spec": channel_spec}
        )

    async def cancel(self, *, projection_id):
        pass


def _input(ws, *, collection_id=None, molecule_ids=None):
    return StartActivityProjectionInput(
        workspace_id=ws, requested_by=uuid.uuid4(),
        collection_id=collection_id, molecule_ids=molecule_ids,
        channel=_channel(), now=_NOW,
    )


@pytest.mark.asyncio
async def test_cache_hit_returns_prior_ready_without_compute():
    ws = uuid.uuid4()
    prior = (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            channel_hash="ch", channel_spec={"column": _COLUMN}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=5, now=_NOW)
    )
    repo = FakeRepo(cached=prior)
    orch = FakeOrchestrator()
    a = uuid.uuid4()
    uc = StartActivityProjection(
        members=FakeStream([[(a, "Fc1ccccc1", 1)]]),
        enricher=FakeEnricher({}), repository=repo, orchestrator=orch, uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=[a]))
    assert out.id == prior.id and out.status == SarActivityProjectionStatus.READY
    assert orch.scheduled == [] and repo.written == {}


@pytest.mark.asyncio
async def test_inline_path_enriches_and_persists_ready():
    ws = uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")},
    }
    repo = FakeRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartActivityProjection(
        members=FakeStream([[(a, "Fc1ccccc1", 1), (b, "CCO", 1)]]),
        enricher=FakeEnricher(table), repository=repo, orchestrator=orch, uow=FakeUoW(),
        inline_threshold=200,
    )
    out = await uc.execute(_input(ws, molecule_ids=[a, b]))
    assert out.status == SarActivityProjectionStatus.READY
    assert out.value_count == 1  # sparse — only 'a'
    assert len(repo.written[out.id]) == 1
    assert orch.scheduled == []


@pytest.mark.asyncio
async def test_async_path_schedules_pending_with_source():
    ws, cid = uuid.uuid4(), uuid.uuid4()
    batch = [(uuid.uuid4(), "Fc1ccccc1", 1) for _ in range(3)]
    repo = FakeRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartActivityProjection(
        members=FakeStream([batch]),
        enricher=FakeEnricher({}), repository=repo, orchestrator=orch, uow=FakeUoW(),
        inline_threshold=2,
    )
    out = await uc.execute(_input(ws, collection_id=cid))
    assert out.status == SarActivityProjectionStatus.PENDING
    assert repo.written == {}
    assert len(orch.scheduled) == 1
    assert orch.scheduled[0]["collection_id"] == cid  # source passed, not expanded ids
    assert orch.scheduled[0]["channel_spec"]["column"] == _COLUMN


@pytest.mark.asyncio
async def test_empty_input_yields_ready_empty():
    ws = uuid.uuid4()
    repo = FakeRepo(cached=None)
    uc = StartActivityProjection(
        members=FakeStream([]), enricher=FakeEnricher({}),
        repository=repo, orchestrator=FakeOrchestrator(), uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=[]))
    assert out.status == SarActivityProjectionStatus.READY
    assert out.value_count == 0


@pytest.mark.asyncio
async def test_inline_failure_marks_projection_failed_and_reraises():
    # The inline path commits RUNNING before enriching; a failure must leave the
    # row FAILED, never orphaned RUNNING.
    ws = uuid.uuid4()
    a = uuid.uuid4()
    repo = FakeRepo(cached=None)

    class BoomEnricher:
        async def enrich_molecules(self, ws_, ids, cols, *, selection_rule, qualifier_handling, run_scopes=None):
            raise RuntimeError("enrich boom")

    uc = StartActivityProjection(
        members=FakeStream([[(a, "Fc1ccccc1", 1)]]),
        enricher=BoomEnricher(), repository=repo, orchestrator=FakeOrchestrator(), uow=FakeUoW(),
        inline_threshold=200,
    )
    with pytest.raises(RuntimeError, match="enrich boom"):
        await uc.execute(_input(ws, molecule_ids=[a]))
    saved = next(iter(repo._by_id.values()))
    assert saved.status == SarActivityProjectionStatus.FAILED
