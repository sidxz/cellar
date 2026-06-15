from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule

_NOW = datetime(2026, 6, 15, tzinfo=UTC)
_COLUMN = "drc:" + str(uuid.uuid4())


def _channel_spec_dict() -> dict:
    return ActivityChannelSpec(
        column=_COLUMN,
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    ).to_spec_dict()


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRepo:
    def __init__(self, proj):
        self._by_id = {proj.id: proj} if proj else {}
        self.written: dict[uuid.UUID, list] = {}

    async def save(self, p):
        self._by_id[p.id] = p

    async def find_by_id(self, pid, *, workspace_id):
        p = self._by_id.get(pid)
        return p if p and p.workspace_id == workspace_id else None

    async def write_values(self, pid, values):
        self.written.setdefault(pid, []).extend(values)


class FakeEnricher:
    def __init__(self, table, *, raise_on_call=False):
        self._table = table
        self._raise = raise_on_call

    async def enrich_molecules(self, ws, ids, cols, *, selection_rule, qualifier_handling, run_scopes=None):
        if self._raise:
            raise RuntimeError("enrich boom")
        return {mid: self._table[mid] for mid in ids if mid in self._table}


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for b in self._batches:
            yield b


def _pending(ws) -> SarActivityProjection:
    return SarActivityProjection.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        channel_hash="ch", channel_spec=_channel_spec_dict(), now=_NOW,
    )


@pytest.mark.asyncio
async def test_run_marks_ready_with_value_count():
    ws = uuid.uuid4()
    proj = _pending(ws)
    a, b = uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")},
    }
    repo = FakeRepo(proj)
    uc = RunActivityProjection(
        members=FakeStream([[(a, "Fc1ccccc1", 1), (b, "CCO", 1)]]),
        enricher=FakeEnricher(table),
        repository=repo,
        uow=FakeUoW(),
    )
    await uc.run(run_id=proj.id, workspace_id=ws, channel_spec=_channel_spec_dict(), molecule_ids=[a, b])
    saved = repo._by_id[proj.id]
    assert saved.status == SarActivityProjectionStatus.READY
    assert saved.value_count == 1  # only 'a' had a scalar (sparse)
    assert len(repo.written[proj.id]) == 1


@pytest.mark.asyncio
async def test_run_marks_failed_and_reraises():
    ws = uuid.uuid4()
    proj = _pending(ws)
    repo = FakeRepo(proj)
    uc = RunActivityProjection(
        members=FakeStream([[(uuid.uuid4(), "Fc1ccccc1", 1)]]),
        enricher=FakeEnricher({}, raise_on_call=True),
        repository=repo,
        uow=FakeUoW(),
    )
    with pytest.raises(RuntimeError, match="enrich boom"):
        await uc.run(run_id=proj.id, workspace_id=ws, channel_spec=_channel_spec_dict(), molecule_ids=[uuid.uuid4()])
    assert repo._by_id[proj.id].status == SarActivityProjectionStatus.FAILED


@pytest.mark.asyncio
async def test_run_skips_when_not_pending():
    ws = uuid.uuid4()
    cancelled = _pending(ws).mark_cancelled(_NOW)
    repo = FakeRepo(cancelled)
    uc = RunActivityProjection(
        members=FakeStream([]), enricher=FakeEnricher({}), repository=repo, uow=FakeUoW()
    )
    await uc.run(run_id=cancelled.id, workspace_id=ws, channel_spec=_channel_spec_dict(), molecule_ids=[])
    assert repo._by_id[cancelled.id].status == SarActivityProjectionStatus.CANCELLED
    assert repo.written == {}
