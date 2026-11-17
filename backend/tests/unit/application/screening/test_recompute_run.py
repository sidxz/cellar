"""RecomputeRun: an edit of the run's data — editors only, never on a locked or approved run."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.readout_calculation_engine import ComputeRunResult
from cellar.application.screening.recompute_run import RecomputeRun, RecomputeRunCommand
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_import_instrument_file import FakeUoW
from tests.unit.domain.screening_assay.test_run import _instrument_run


def _harness(status=RunStatus.COMPLETED, locked=False, computed=None):  # type: ignore[no-untyped-def]
    run, _ = _instrument_run(status=status, locked=locked)
    uow, run_repo, engine = FakeUoW([run]), AsyncMock(), AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    engine.compute_for_run = AsyncMock(
        return_value=computed or Success(ComputeRunResult(computed_readouts=[]))
    )
    uc = RecomputeRun(
        uow=uow, run_repo=run_repo, calculation_engine=engine, dispatcher=AsyncMock()
    )
    cmd = RecomputeRunCommand(workspace_id=run.workspace_id, run_id=run.id)
    return uc, cmd, run, uow, run_repo, engine


async def test_an_editor_recomputes_in_one_transaction_with_the_run_saved():
    uc, cmd, run, uow, run_repo, engine = _harness()
    result = await uc(cmd, auth=FakeAuth(workspace_id=run.workspace_id))
    assert isinstance(result, Success)
    run_repo.save.assert_awaited_once_with(run)
    engine.compute_for_run.assert_awaited_once_with(
        run.id, workspace_id=run.workspace_id, fit_overrides=None
    )
    assert uow.committed


@pytest.mark.parametrize(
    ("status", "locked"), [(RunStatus.APPROVED, False), (RunStatus.COMPLETED, True)]
)
async def test_a_locked_or_approved_run_is_refused(status, locked):
    uc, cmd, run, uow, _, engine = _harness(status=status, locked=locked)
    result = await uc(cmd, auth=FakeAuth(workspace_id=run.workspace_id))
    assert isinstance(result.failure(), ConflictError)
    engine.compute_for_run.assert_not_awaited()
    assert uow.committed is False


async def test_a_viewer_or_another_workspace_is_refused():
    uc, cmd, run, _, _, engine = _harness()
    with pytest.raises(AuthorizationError):
        await uc(cmd, auth=FakeAuth(workspace_id=run.workspace_id, role="viewer"))
    with pytest.raises(NotFoundError):
        await uc(cmd, auth=FakeAuth(workspace_id=uuid.uuid4()))
    engine.compute_for_run.assert_not_awaited()


async def test_a_failed_calculation_commits_nothing():
    uc, cmd, run, uow, _, _ = _harness(computed=Failure(ValidationError("no controls")))
    result = await uc(cmd, auth=FakeAuth(workspace_id=run.workspace_id))
    assert isinstance(result, Failure)
    assert uow.committed is False
