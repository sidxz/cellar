"""Unit tests for CreateReadoutData — the single-row readout entry path.

The one-run-one-shape rule is a property of the run, not of the route: a welled
run's values hang off a well, a well-less run's off the compound/batch alone.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

from returns.result import Failure, Success

from cellar.application.screening.create_readout_data import (
    CreateReadoutData,
    CreateReadoutDataCommand,
)
from cellar.domain.screening_assay.data_lock_guard import DataLockGuard
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth


class FakeUoW:
    """Minimal fake UoW."""

    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


def _make_run(workspace_id: uuid.UUID, *, welled: bool) -> Run:
    run = Run(
        workspace_id=workspace_id,
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 1, 15),
        operator=uuid.uuid4(),
    )
    if welled:
        plate = Plate(run_id=run.id, plate_number=1)
        run.plates = [plate]
        run.wells = [Well(plate_id=plate.id, row="A", column=1)]
    return run


def _build(run: Run) -> tuple[CreateReadoutData, FakeUoW, AsyncMock]:
    uow = FakeUoW()
    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    run_repo.is_locked = AsyncMock(return_value=False)
    repo = AsyncMock()
    uc = CreateReadoutData(
        uow=uow,  # type: ignore[arg-type]
        repo=repo,
        guard=DataLockGuard(run_repo),
        dispatcher=AsyncMock(),
        run_repo=run_repo,
    )
    return uc, uow, repo


def _command(run: Run, *, well_id: uuid.UUID | None) -> CreateReadoutDataCommand:
    return CreateReadoutDataCommand(
        workspace_id=run.workspace_id,
        run_id=run.id,
        well_id=well_id,
        molecule_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        value_numeric=5.0,
    )


class TestCreateReadoutDataRunShape:
    async def test_welled_run_requires_a_well_id(self) -> None:
        run = _make_run(uuid.uuid4(), welled=True)
        auth = FakeAuth(role="editor", workspace_id=run.workspace_id)
        uc, uow, repo = _build(run)

        result = await uc(_command(run, well_id=None), auth=auth)

        assert isinstance(result, Failure)
        error = result.failure()
        assert isinstance(error, ValidationError)
        assert "run has plates; well_id is required" in str(error)
        repo.save.assert_not_awaited()
        assert not uow.committed

    async def test_wellless_run_rejects_a_well_id(self) -> None:
        run = _make_run(uuid.uuid4(), welled=False)
        auth = FakeAuth(role="editor", workspace_id=run.workspace_id)
        uc, uow, repo = _build(run)

        result = await uc(_command(run, well_id=uuid.uuid4()), auth=auth)

        assert isinstance(result, Failure)
        error = result.failure()
        assert isinstance(error, ValidationError)
        assert "run has no plates; well_id must be omitted" in str(error)
        repo.save.assert_not_awaited()
        assert not uow.committed

    async def test_matching_shape_still_writes(self) -> None:
        """The guard must not over-fire: a well-bound row on a welled run lands."""
        run = _make_run(uuid.uuid4(), welled=True)
        auth = FakeAuth(role="editor", workspace_id=run.workspace_id)
        uc, uow, repo = _build(run)
        well_id = run.wells[0].id

        result = await uc(_command(run, well_id=well_id), auth=auth)

        assert isinstance(result, Success), result
        assert result.unwrap().well_id == well_id
        repo.save.assert_awaited_once()
        assert uow.committed
