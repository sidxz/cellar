from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.run_decomposition import RunDecomposition, ready_counts
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
    def __init__(self, run: RGroupDecompositionRun | None) -> None:
        self._runs: dict[uuid.UUID, RGroupDecompositionRun] = {}
        if run is not None:
            self._runs[run.id] = run
        self.written: dict[uuid.UUID, list[RGroupAssignment]] = {}

    async def save(self, run):
        self._runs[run.id] = run

    async def find_by_id(self, run_id, *, workspace_id):
        run = self._runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return None
        return run

    async def write_assignments(self, run_id, assignments):
        self.written[run_id] = list(assignments)


class FakeSession:
    def __init__(self, result: RGroupDecompositionResult, *, raise_on_finish=False):
        self._result = result
        self._raise = raise_on_finish
        self.added: list[tuple] = []

    def add(self, molecule_id, smiles):
        self.added.append((molecule_id, smiles))
        return True

    def finish(self):
        if self._raise:
            raise RuntimeError("rdkit boom")
        return self._result


class FakeDecomposer:
    def __init__(self, session: FakeSession):
        self._session = session

    def canonical_core_smiles(self, core_smiles):
        return core_smiles

    def session(self, *, core_smiles):
        return self._session


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for batch in self._batches:
            yield batch


def _pending_run(ws: uuid.UUID) -> RGroupDecompositionRun:
    return RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="m",
        core_smiles="c1ccccc1",
        core_hash="ch",
        now=_NOW,
    )


def test_ready_counts_bridge():
    a, b = uuid.uuid4(), uuid.uuid4()
    result = RGroupDecompositionResult(
        core_smiles="c1ccccc1",
        rgroup_labels=["R1"],
        assignments=[RGroupAssignment(molecule_id=a, rgroups={"R1": "F"})],
        unmatched_ids=[b],
    )
    assert ready_counts(result) == (1, 1, 2)


@pytest.mark.asyncio
async def test_run_marks_ready_with_assignments_and_counts():
    ws = uuid.uuid4()
    run = _pending_run(ws)
    matched, unmatched = uuid.uuid4(), uuid.uuid4()
    result = RGroupDecompositionResult(
        core_smiles="c1ccccc1",
        rgroup_labels=["R1"],
        assignments=[RGroupAssignment(molecule_id=matched, rgroups={"R1": "F"})],
        unmatched_ids=[unmatched],
    )
    repo = FakeRunRepo(run)
    uc = RunDecomposition(
        members=FakeStream([[(matched, "Fc1ccccc1", 1), (unmatched, "CCO", 1)]]),
        decomposer=FakeDecomposer(FakeSession(result)),
        repository=repo,
        uow=FakeUoW(),
    )

    await uc.run(run_id=run.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[matched, unmatched])

    saved = repo._runs[run.id]
    assert saved.status == RGroupDecompositionRunStatus.READY
    assert saved.rgroup_labels == ["R1"]
    assert (saved.matched_count, saved.unmatched_count, saved.total_count) == (1, 1, 2)
    assert repo.written[run.id][0].molecule_id == matched


@pytest.mark.asyncio
async def test_run_null_smiles_member_is_added_as_empty_string():
    ws = uuid.uuid4()
    run = _pending_run(ws)
    structureless = uuid.uuid4()
    session = FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1", unmatched_ids=[structureless]))
    uc = RunDecomposition(
        members=FakeStream([[(structureless, None, 1)]]),
        decomposer=FakeDecomposer(session),
        repository=FakeRunRepo(run),
        uow=FakeUoW(),
    )
    await uc.run(run_id=run.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[structureless])
    assert session.added == [(structureless, "")]  # None -> "" so the session routes it to unmatched


@pytest.mark.asyncio
async def test_run_marks_failed_and_reraises_on_exception():
    ws = uuid.uuid4()
    run = _pending_run(ws)
    repo = FakeRunRepo(run)
    uc = RunDecomposition(
        members=FakeStream([[(uuid.uuid4(), "Fc1ccccc1", 1)]]),
        decomposer=FakeDecomposer(FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"), raise_on_finish=True)),
        repository=repo,
        uow=FakeUoW(),
    )
    with pytest.raises(RuntimeError, match="rdkit boom"):
        await uc.run(run_id=run.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[uuid.uuid4()])
    assert repo._runs[run.id].status == RGroupDecompositionRunStatus.FAILED
    assert "rdkit boom" in (repo._runs[run.id].error_message or "")


@pytest.mark.asyncio
async def test_run_skips_when_not_pending():
    ws = uuid.uuid4()
    cancelled = _pending_run(ws).mark_cancelled(_NOW)
    repo = FakeRunRepo(cancelled)
    session = FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"))
    uc = RunDecomposition(
        members=FakeStream([]),
        decomposer=FakeDecomposer(session),
        repository=repo,
        uow=FakeUoW(),
    )
    await uc.run(run_id=cancelled.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[])
    assert repo._runs[cancelled.id].status == RGroupDecompositionRunStatus.CANCELLED
    assert session.added == []  # never decomposed a cancelled run
