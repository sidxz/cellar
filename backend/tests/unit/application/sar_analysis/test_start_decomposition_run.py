from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.start_decomposition_run import (
    StartDecompositionRun,
    StartDecompositionRunInput,
)
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRunRepo:
    def __init__(self, cached: RGroupDecompositionRun | None = None) -> None:
        self._runs: dict[uuid.UUID, RGroupDecompositionRun] = {}
        self._cached = cached
        self.written: dict[uuid.UUID, list[RGroupAssignment]] = {}

    async def save(self, run):
        self._runs[run.id] = run

    async def find_by_id(self, run_id, *, workspace_id):
        return self._runs.get(run_id)

    async def find_cached(self, *, workspace_id, membership_hash, core_hash):
        return self._cached

    async def write_assignments(self, run_id, assignments):
        self.written[run_id] = list(assignments)


class FakeSession:
    def __init__(self, result: RGroupDecompositionResult):
        self._result = result
        self.added: list[tuple] = []

    def add(self, molecule_id, smiles):
        self.added.append((molecule_id, smiles))
        return True

    def finish(self):
        return self._result


class FakeDecomposer:
    def __init__(self, session: FakeSession | None = None):
        self._session = session or FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"))

    def canonical_core_smiles(self, core_smiles):
        return f"canon::{core_smiles}"

    def session(self, *, core_smiles):
        return self._session


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for batch in self._batches:
            yield batch


class FakeOrchestrator:
    def __init__(self):
        self.scheduled: list[dict] = []

    async def schedule(self, *, run_id, workspace_id, core_smiles, collection_id=None, molecule_ids=None):
        self.scheduled.append(
            {
                "run_id": run_id,
                "workspace_id": workspace_id,
                "core_smiles": core_smiles,
                "collection_id": collection_id,
                "molecule_ids": molecule_ids,
            }
        )

    async def cancel(self, *, run_id):
        pass


def _input(ws, *, collection_id=None, molecule_ids=None):
    return StartDecompositionRunInput(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        collection_id=collection_id,
        molecule_ids=molecule_ids,
        core_smiles="c1ccccc1",
        now=_NOW,
    )


@pytest.mark.asyncio
async def test_cache_hit_returns_prior_ready_run_without_compute():
    ws = uuid.uuid4()
    prior = (
        RGroupDecompositionRun.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(rgroup_labels=["R1"], matched_count=3, unmatched_count=0, total_count=3, now=_NOW)
    )
    repo = FakeRunRepo(cached=prior)
    orch = FakeOrchestrator()
    ids = [uuid.uuid4()]
    uc = StartDecompositionRun(
        members=FakeStream([[(ids[0], "Fc1ccccc1", 1)]]),
        decomposer=FakeDecomposer(),
        repository=repo,
        orchestrator=orch,
        uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=ids))
    assert out.id == prior.id
    assert out.status == RGroupDecompositionRunStatus.READY
    assert orch.scheduled == []
    assert repo.written == {}  # no new compute


@pytest.mark.asyncio
async def test_inline_path_computes_persists_ready_and_assignments():
    ws = uuid.uuid4()
    matched, unmatched = uuid.uuid4(), uuid.uuid4()
    result = RGroupDecompositionResult(
        core_smiles="c1ccccc1",
        rgroup_labels=["R1"],
        assignments=[RGroupAssignment(molecule_id=matched, rgroups={"R1": "F"})],
        unmatched_ids=[unmatched],
    )
    repo = FakeRunRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartDecompositionRun(
        members=FakeStream([[(matched, "Fc1ccccc1", 1), (unmatched, "CCO", 1)]]),
        decomposer=FakeDecomposer(FakeSession(result)),
        repository=repo,
        orchestrator=orch,
        uow=FakeUoW(),
        inline_threshold=200,
    )
    out = await uc.execute(_input(ws, molecule_ids=[matched, unmatched]))
    assert out.status == RGroupDecompositionRunStatus.READY
    assert out.rgroup_labels == ["R1"]
    assert (out.matched_count, out.unmatched_count, out.total_count) == (1, 1, 2)
    assert repo.written[out.id][0].molecule_id == matched
    assert orch.scheduled == []  # inline, not scheduled


@pytest.mark.asyncio
async def test_async_path_schedules_pending_run_above_threshold():
    ws = uuid.uuid4()
    cid = uuid.uuid4()
    batch = [(uuid.uuid4(), "Fc1ccccc1", 1) for _ in range(3)]
    repo = FakeRunRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartDecompositionRun(
        members=FakeStream([batch]),
        decomposer=FakeDecomposer(),
        repository=repo,
        orchestrator=orch,
        uow=FakeUoW(),
        inline_threshold=2,
    )
    out = await uc.execute(_input(ws, collection_id=cid))
    assert out.status == RGroupDecompositionRunStatus.PENDING
    assert repo.written == {}  # nothing computed inline
    assert len(orch.scheduled) == 1
    assert orch.scheduled[0]["run_id"] == out.id
    assert orch.scheduled[0]["collection_id"] == cid  # source passed, not expanded ids


@pytest.mark.asyncio
async def test_empty_input_yields_ready_empty_run():
    ws = uuid.uuid4()
    repo = FakeRunRepo(cached=None)
    uc = StartDecompositionRun(
        members=FakeStream([]),
        decomposer=FakeDecomposer(FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"))),
        repository=repo,
        orchestrator=FakeOrchestrator(),
        uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=[]))
    assert out.status == RGroupDecompositionRunStatus.READY
    assert out.total_count == 0
    assert out.rgroup_labels == []


@pytest.mark.asyncio
async def test_inline_failure_marks_run_failed_and_reraises():
    # The inline path commits RUNNING before decomposing; a failure must leave
    # the row FAILED, never orphaned RUNNING.
    ws = uuid.uuid4()
    repo = FakeRunRepo(cached=None)

    class BoomSession(FakeSession):
        def finish(self):
            raise RuntimeError("rdkit boom")

    uc = StartDecompositionRun(
        members=FakeStream([[(uuid.uuid4(), "Fc1ccccc1", 1)]]),
        decomposer=FakeDecomposer(BoomSession(RGroupDecompositionResult(core_smiles="c1ccccc1"))),
        repository=repo,
        orchestrator=FakeOrchestrator(),
        uow=FakeUoW(),
        inline_threshold=200,
    )
    with pytest.raises(RuntimeError, match="rdkit boom"):
        await uc.execute(_input(ws, molecule_ids=[uuid.uuid4()]))
    saved = next(iter(repo._runs.values()))
    assert saved.status == RGroupDecompositionRunStatus.FAILED
