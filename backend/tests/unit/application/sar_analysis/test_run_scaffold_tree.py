"""Unit tests for RunScaffoldTree — proves the runner's lifecycle invariants
(three of the five are direct bug-fix regression guards: b, c, e).

Scaffold has NO reset step (header-only result; no child rows), so the only
lifecycle steps are: claim -> builder.execute -> finalize_if_still_running.

(a) test_run_marks_ready_with_result
    Happy path: PENDING -> RUNNING -> READY, result attached.

(b) test_run_reraises_without_marking_failed
    Builder raises; runner re-raises AND leaves job RUNNING. FAILED is recorded
    at the orchestration boundary (NullScaffoldTreeOrchestrator / Temporal
    workflow), not here, so a retry can re-enter and recover.

(c) test_run_reclaims_running_without_error
    Job is already RUNNING (Temporal retry). claim_job re-enters without raising
    InvalidJobTransition (the old unconditional mark_running would have).
    Execution reaches READY.

(d) test_run_respects_concurrent_cancel
    A cancel commits mid-build (FakeBuilder cancels the job in-repo before
    returning). The runner re-reads via finalize_if_still_running and does NOT
    clobber the CANCELLED state — it stays CANCELLED.

(e) test_run_skips_when_terminal
    A CANCELLED job is a no-op: claim_job returns False, builder never called.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.build_scaffold_network import BuildScaffoldNetworkInput
from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult, ScaffoldTreeStats
from cellar.domain.shared.async_job import AsyncJobStatus

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeJobRepo:
    """Dict-backed in-memory repo; models the shared async-job repo contract."""

    def __init__(self, job: ScaffoldTreeJob | None = None) -> None:
        self._jobs: dict[uuid.UUID, ScaffoldTreeJob] = {}
        if job is not None:
            self._jobs[job.id] = job

    async def save(self, job: ScaffoldTreeJob) -> None:
        self._jobs[job.id] = job

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, job_id: uuid.UUID
    ) -> ScaffoldTreeJob | None:
        job = self._jobs.get(job_id)
        if job is None or job.workspace_id != workspace_id:
            return None
        return job


def _minimal_result() -> ScaffoldTreeResult:
    return ScaffoldTreeResult(
        nodes=[],
        edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=5, cache_hit=False),
    )


class FakeBuilder:
    """Returns a fixed result, or raises if constructed with boom=True."""

    def __init__(self, result: ScaffoldTreeResult | None = None, *, boom: bool = False) -> None:
        self._result = result or _minimal_result()
        self._boom = boom
        self.called_with: BuildScaffoldNetworkInput | None = None

    async def execute(self, input: BuildScaffoldNetworkInput) -> ScaffoldTreeResult:
        self.called_with = input
        if self._boom:
            raise RuntimeError("builder boom")
        return self._result


class CancellingBuilder:
    """Builder whose execute() cancels the job in the repo before returning.

    Models the race where a user cancel commits between claim and finalize.
    """

    def __init__(self, result: ScaffoldTreeResult, repo: FakeJobRepo, job: ScaffoldTreeJob) -> None:
        self._result = result
        self._repo = repo
        self._job = job

    async def execute(self, input: BuildScaffoldNetworkInput) -> ScaffoldTreeResult:
        # Simulate the cancel committing while the build is in flight.
        self._repo._jobs[self._job.id].mark_cancelled(_NOW)
        return self._result


def _pending_job(ws: uuid.UUID) -> ScaffoldTreeJob:
    return ScaffoldTreeJob.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        ids_hash="ids-hash",
        now=_NOW,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_marks_ready_with_result():
    """Happy path: PENDING job -> runner -> READY with builder's result."""
    ws = uuid.uuid4()
    job = _pending_job(ws)
    result = _minimal_result()
    builder = FakeBuilder(result)
    repo = FakeJobRepo(job)

    uc = RunScaffoldTree(builder=builder, repository=repo, uow=FakeUoW())
    await uc.run(job_id=job.id, workspace_id=ws, molecule_ids=[uuid.uuid4()])

    saved = repo._jobs[job.id]
    assert saved.status == AsyncJobStatus.READY
    assert saved.result is result
    assert builder.called_with is not None
    assert builder.called_with.workspace_id == ws


@pytest.mark.asyncio
async def test_run_reraises_without_marking_failed():
    """Bug (b) fix: the runner re-raises and leaves the job RUNNING.

    FAILED is recorded at the orchestration boundary (NullScaffoldTreeOrchestrator
    / Temporal workflow) so a retry can re-enter and recover.
    """
    ws = uuid.uuid4()
    job = _pending_job(ws)
    repo = FakeJobRepo(job)

    uc = RunScaffoldTree(
        builder=FakeBuilder(boom=True),
        repository=repo,
        uow=FakeUoW(),
    )
    with pytest.raises(RuntimeError, match="builder boom"):
        await uc.run(job_id=job.id, workspace_id=ws, molecule_ids=[uuid.uuid4()])

    assert repo._jobs[job.id].status == AsyncJobStatus.RUNNING


@pytest.mark.asyncio
async def test_run_reclaims_running_without_error():
    """Bug (c) fix: a RUNNING job (Temporal retry) is reclaimed without raising.

    The old unconditional mark_running would have raised InvalidJobTransition
    because the job was already RUNNING. claim_job now re-claims silently.
    """
    ws = uuid.uuid4()
    job = _pending_job(ws)
    job.mark_running(_NOW)  # simulate: a prior attempt already claimed it
    result = _minimal_result()
    repo = FakeJobRepo(job)

    uc = RunScaffoldTree(builder=FakeBuilder(result), repository=repo, uow=FakeUoW())
    await uc.run(job_id=job.id, workspace_id=ws, molecule_ids=[uuid.uuid4()])

    saved = repo._jobs[job.id]
    assert saved.status == AsyncJobStatus.READY
    assert saved.result is result


@pytest.mark.asyncio
async def test_run_respects_concurrent_cancel():
    """Bug (e) fix: a cancel that commits mid-build is honored by the runner.

    finalize_if_still_running re-reads the job before marking READY; if it is
    no longer RUNNING it bails, so the CANCELLED state is preserved.
    """
    ws = uuid.uuid4()
    job = _pending_job(ws)
    repo = FakeJobRepo(job)
    result = _minimal_result()

    uc = RunScaffoldTree(
        builder=CancellingBuilder(result, repo, job),
        repository=repo,
        uow=FakeUoW(),
    )
    await uc.run(job_id=job.id, workspace_id=ws, molecule_ids=[uuid.uuid4()])

    assert repo._jobs[job.id].status == AsyncJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_run_skips_when_terminal():
    """A CANCELLED job is a no-op: claim_job returns False, builder never called."""
    ws = uuid.uuid4()
    job = _pending_job(ws)
    job.mark_cancelled(_NOW)
    builder = FakeBuilder()
    repo = FakeJobRepo(job)

    uc = RunScaffoldTree(builder=builder, repository=repo, uow=FakeUoW())
    await uc.run(job_id=job.id, workspace_id=ws, molecule_ids=[uuid.uuid4()])

    assert repo._jobs[job.id].status == AsyncJobStatus.CANCELLED
    assert builder.called_with is None  # builder never called
