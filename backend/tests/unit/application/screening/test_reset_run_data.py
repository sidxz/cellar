"""Unit tests for ResetRunData use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.reset_run_data import (
    ResetRunData,
    ResetRunDataCommand,
)
from cellar.domain.screening_assay.enums import RunStatus, WellType
from cellar.domain.screening_assay.events import RunDataReset
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.errors import ConflictError, NotFoundError
from cellar.domain.shared.events import DomainEvent


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False
        self.events_to_return: list[DomainEvent] = []

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return list(self.events_to_return)

    async def rollback(self) -> None:  # pragma: no cover
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


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


def _make_run(
    workspace_id: uuid.UUID,
    *,
    status: RunStatus = RunStatus.IN_PROGRESS,
    locked: bool = False,
    with_plates: bool = True,
) -> Run:
    run = Run(
        workspace_id=workspace_id,
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 5, 6),
        operator=uuid.uuid4(),
        status=status,
        is_locked=locked,
    )
    if with_plates:
        plate = Plate(
            run_id=run.id,
            plate_number=1,
            format=PlateFormat.F96,
            plate_map={"name": "P1"},
        )
        run.plates.append(plate)
        run.wells.append(
            Well(plate_id=plate.id, row="A", column=1, well_type=WellType.SAMPLE)
        )
        run.wells.append(
            Well(plate_id=plate.id, row="A", column=2, well_type=WellType.SAMPLE)
        )
        run.qc_metrics = {"z_prime": {"plate-1": 0.7}}
    return run


def _build_uc(
    run: Run | None,
    *,
    readouts_deleted: int = 0,
    curves_for_run: list | None = None,
):
    uow = FakeUoW()
    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    run_repo.save = AsyncMock()

    readout_repo = AsyncMock()
    readout_repo.delete_for_run = AsyncMock(return_value=readouts_deleted)

    curve_repo = AsyncMock()
    curve_repo.find_by_run = AsyncMock(return_value=curves_for_run or [])
    curve_repo.delete_by_run = AsyncMock(return_value=None)

    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()

    uc = ResetRunData(
        uow=uow,
        run_repo=run_repo,
        readout_data_repo=readout_repo,
        curve_repo=curve_repo,
        dispatcher=dispatcher,
    )
    return uc, uow, run_repo, readout_repo, curve_repo, dispatcher


# ---------------------------------------------------------------------------
# Happy path + state preservation
# ---------------------------------------------------------------------------


class TestResetRunData:
    @pytest.mark.asyncio
    async def test_clears_plates_wells_qc(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, uow, run_repo, _, _, _ = _build_uc(run, readouts_deleted=4)

        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Success), result
        out = result.unwrap()
        assert out.plates_deleted == 1
        assert out.wells_deleted == 2
        assert out.readouts_deleted == 4
        assert run.plates == []
        assert run.wells == []
        assert run.qc_metrics == {}
        run_repo.save.assert_awaited_once()
        assert uow.committed

    @pytest.mark.asyncio
    async def test_preserves_run_metadata(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        original_protocol_id = run.protocol_id
        original_run_date = run.run_date
        original_operator = run.operator
        original_id = run.id

        uc, _, _, _, _, _ = _build_uc(run)
        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Success), result
        # Run metadata untouched
        assert run.id == original_id
        assert run.protocol_id == original_protocol_id
        assert run.run_date == original_run_date
        assert run.operator == original_operator

    @pytest.mark.asyncio
    async def test_emits_event(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, _, _, _, _, _ = _build_uc(run, readouts_deleted=3)

        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Success), result
        events = run.collect_events()
        reset_events = [e for e in events if isinstance(e, RunDataReset)]
        assert len(reset_events) == 1
        ev = reset_events[0]
        assert ev.aggregate_id == run.id
        assert ev.workspace_id == auth.workspace_id
        assert ev.plates_deleted == 1
        assert ev.wells_deleted == 2
        assert ev.readouts_deleted == 3

    # ---------------------------------------------------------------------
    # Guards
    # ---------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_rejects_locked_run(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, locked=True)
        uc, _, _, _, _, _ = _build_uc(run)
        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        # State unchanged
        assert len(run.plates) == 1
        assert run.qc_metrics != {}

    @pytest.mark.asyncio
    async def test_rejects_completed_run(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, status=RunStatus.COMPLETED)
        uc, _, _, _, _, _ = _build_uc(run)
        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)

    @pytest.mark.asyncio
    async def test_rejects_approved_run(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, status=RunStatus.APPROVED)
        uc, _, _, _, _, _ = _build_uc(run)
        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_rejects_when_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, _, _, _, _, _ = _build_uc(None)
        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=uuid.uuid4()),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_allows_draft_run(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, status=RunStatus.DRAFT)
        uc, _, _, _, _, _ = _build_uc(run)
        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_calls_dispatcher_after_commit(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, _, _, _, _, dispatcher = _build_uc(run)
        result = await uc(
            ResetRunDataCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )
        assert isinstance(result, Success)
        dispatcher.dispatch_all.assert_awaited_once()
