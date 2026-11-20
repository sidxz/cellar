from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Failure

from cellar.application.sar_analysis.decomposition_assignments import (
    FetchDecompositionAssignments,
    FetchDecompositionAssignmentsInput,
)
from cellar.application.sar_analysis.decomposition_rows import DecompositionRow
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.shared.errors import NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth

_NOW = datetime(2026, 11, 16, tzinfo=UTC)
_WS = uuid.uuid4()


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRunRepo:
    def __init__(self, run):
        self._run = run

    async def find_by_id_in_workspace(self, workspace_id, rid):
        return (
            self._run if self._run.id == rid and self._run.workspace_id == workspace_id else None
        )


class SpyReader:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[dict] = []

    async def fetch_assignments(self, run_id, *, workspace_id):
        self.calls.append({"run_id": run_id, "workspace_id": workspace_id})
        return {r.molecule_id: r.rgroups for r in self._rows}


def _row(i: int) -> DecompositionRow:
    return DecompositionRow(
        molecule_id=uuid.uuid4(),
        smiles="c1ccccc1",
        registration_number=f"CV-{i}",
        name=f"CV-{i}",
        rgroups={"R1": f"[*:1]C{i}"},
        molecular_weight=None,
        logp=None,
        tpsa=None,
    )


def _run(*, ready: bool, matched: int = 0) -> RGroupDecompositionRun:
    run = RGroupDecompositionRun.create(
        workspace_id=_WS,
        requested_by=uuid.uuid4(),
        membership_hash="m",
        core_smiles="c1ccccc1",
        core_hash="ch",
        now=_NOW,
    )
    if ready:
        run.mark_running(_NOW)
        run.mark_ready(
            rgroup_labels=["R1", "R2"],
            matched_count=matched,
            unmatched_count=3,
            total_count=matched + 3,
            now=_NOW,
        )
    return run


def _uc(run, reader) -> FetchDecompositionAssignments:
    return FetchDecompositionAssignments(repository=FakeRunRepo(run), reader=reader, uow=FakeUoW())


@pytest.mark.asyncio
async def test_reads_every_assignment_in_one_call_past_the_page_cap():
    rows = [_row(i) for i in range(250)]
    run, reader = _run(ready=True, matched=250), SpyReader(rows)

    out = await _uc(run, reader).execute(
        FetchDecompositionAssignmentsInput(run_id=run.id, workspace_id=_WS)
    )

    res = out.unwrap()
    assert reader.calls == [{"run_id": run.id, "workspace_id": _WS}]
    assert len(res.assignments) == 250
    assert res.assignments[rows[7].molecule_id] == {"R1": "[*:1]C7"}
    assert (res.core_smiles, res.labels) == ("c1ccccc1", ["R1", "R2"])


@pytest.mark.asyncio
async def test_a_run_with_no_matches_has_no_assignments():
    run, reader = _run(ready=True, matched=0), SpyReader([])

    out = await _uc(run, reader).execute(
        FetchDecompositionAssignmentsInput(run_id=run.id, workspace_id=_WS)
    )

    assert out.unwrap().assignments == {}


@pytest.mark.asyncio
async def test_unknown_run_is_not_found():
    run, reader = _run(ready=True, matched=1), SpyReader([])

    out = await _uc(run, reader).execute(
        FetchDecompositionAssignmentsInput(run_id=uuid.uuid4(), workspace_id=_WS)
    )

    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)
    assert reader.calls == []


@pytest.mark.asyncio
async def test_a_run_of_another_workspace_is_not_found():
    run, reader = _run(ready=True, matched=1), SpyReader([_row(0)])

    out = await _uc(run, reader).execute(
        FetchDecompositionAssignmentsInput(run_id=run.id, workspace_id=uuid.uuid4())
    )

    assert isinstance(out.failure(), NotFoundError)
    assert reader.calls == []


@pytest.mark.asyncio
async def test_a_caller_from_another_workspace_is_refused_before_any_read():
    run, reader = _run(ready=True, matched=1), SpyReader([_row(0)])

    with pytest.raises(NotFoundError):
        await _uc(run, reader).execute(
            FetchDecompositionAssignmentsInput(run_id=run.id, workspace_id=_WS),
            auth=FakeAuth(role="viewer", workspace_id=uuid.uuid4()),
        )
    assert reader.calls == []


@pytest.mark.asyncio
async def test_a_pending_run_is_not_ready():
    run, reader = _run(ready=False), SpyReader([])

    out = await _uc(run, reader).execute(
        FetchDecompositionAssignmentsInput(run_id=run.id, workspace_id=_WS),
        auth=FakeAuth(role="viewer", workspace_id=_WS),
    )

    err = out.failure()
    assert isinstance(err, ValidationError)
    assert reader.calls == []
