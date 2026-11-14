"""Unit tests for the SetRunHitCriteria / ResetRunHitCriteria use cases.

Covers recording a per-run hit-criteria decision (incl. the empty-list "show
all" decision), reverting to unset, not-found handling, and the locked-run
guard propagating from the domain.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.set_run_hit_criteria import (
    ResetRunHitCriteria,
    ResetRunHitCriteriaCommand,
    SetRunHitCriteria,
    SetRunHitCriteriaCommand,
)
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutAggregation, ReadoutDataType
from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.hit_criterion import HitCriterion


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

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


def _make_run(workspace_id: uuid.UUID, **kwargs) -> Run:
    defaults = dict(
        workspace_id=workspace_id,
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 6, 9),
        operator=uuid.uuid4(),
    )
    defaults.update(kwargs)
    return Run.create(**defaults)


def _melt_rd(name: str, measure: MeltMeasure) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=ReadoutDataType.NUMERIC,
        unit="°C",
        aggregation=ReadoutAggregation.MEAN,
        melt_config=MeltReadoutConfig(
            window="Main", measure=measure, channel_key="ratio", low=50.0, high=85.0
        ),
    )


def _thermal_protocol(workspace_id: uuid.UUID) -> Protocol:
    return Protocol.create(
        workspace_id=workspace_id,
        name="Thermal shift",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            _melt_rd("ΔTm (Main)", MeltMeasure.DELTA_TM),
            _melt_rd("Max ΔTm (Main)", MeltMeasure.MAX_DELTA_TM),
        ],
    )


def _build_set(
    run: Run | None, protocol: Protocol | None = None
) -> tuple[SetRunHitCriteria, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    repo.save = AsyncMock()
    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(
        return_value=protocol or (_thermal_protocol(run.workspace_id) if run else None)
    )
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    uc = SetRunHitCriteria(
        uow=FakeUoW(), repo=repo, dispatcher=dispatcher, protocol_repo=protocol_repo
    )
    return uc, repo, dispatcher


def _build_reset(run: Run | None) -> tuple[ResetRunHitCriteria, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    repo.save = AsyncMock()
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    return ResetRunHitCriteria(uow=FakeUoW(), repo=repo, dispatcher=dispatcher), repo, dispatcher


class TestSetRunHitCriteria:
    @pytest.mark.asyncio
    async def test_accepts_outside_on_delta_tm(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, _, _ = _build_set(run)
        rule = HitCriterion(readout_name="ΔTm (Main)", operator="not_between", value=[-2.0, 2.0])

        result = await uc(
            SetRunHitCriteriaCommand(
                workspace_id=auth.workspace_id, run_id=run.id, criteria=[rule]
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert run.hit_criteria == [rule] and run.hit_criteria_set_by == auth.user_id

    @pytest.mark.asyncio
    async def test_refuses_a_series_value(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, repo, _ = _build_set(run)
        rule = HitCriterion(readout_name="Max ΔTm (Main)", operator="lt", value=-2.0)

        result = await uc(
            SetRunHitCriteriaCommand(
                workspace_id=auth.workspace_id, run_id=run.id, criteria=[rule]
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        assert "Max ΔTm (Main)" in str(result.failure())
        assert run.hit_criteria is None
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_records_criteria_and_actor(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, repo, _ = _build_set(run)
        criteria = [HitCriterion(readout_name="% Inhibition", operator="gt", value=50.0)]

        result = await uc(
            SetRunHitCriteriaCommand(
                workspace_id=auth.workspace_id, run_id=run.id, criteria=criteria
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert run.hit_criteria == criteria
        assert run.hit_criteria_set_by == auth.user_id
        assert run.hit_criteria_set_at is not None
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_criteria_is_a_recorded_show_all_decision(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, _, _ = _build_set(run)

        result = await uc(
            SetRunHitCriteriaCommand(workspace_id=auth.workspace_id, run_id=run.id, criteria=[]),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert run.hit_criteria == []
        assert run.hit_criteria is not None
        assert run.hit_criteria_set_by == auth.user_id

    @pytest.mark.asyncio
    async def test_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, _, dispatcher = _build_set(None)

        result = await uc(
            SetRunHitCriteriaCommand(
                workspace_id=auth.workspace_id, run_id=uuid.uuid4(), criteria=[]
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        dispatcher.dispatch_all.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_locked_run_guard_propagates(self) -> None:
        auth = FakeAuth()
        run = Run(
            workspace_id=auth.workspace_id,
            protocol_id=uuid.uuid4(),
            run_date=date(2026, 6, 9),
            operator=uuid.uuid4(),
            is_locked=True,
        )
        uc, _, _ = _build_set(run)

        with pytest.raises(ConflictError, match="locked"):
            await uc(
                SetRunHitCriteriaCommand(
                    workspace_id=auth.workspace_id, run_id=run.id, criteria=[]
                ),
                auth=auth,
            )


class TestResetRunHitCriteria:
    @pytest.mark.asyncio
    async def test_reverts_to_unset(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        run.set_hit_criteria(
            [HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
            set_by=auth.user_id,
        )
        uc, repo, _ = _build_reset(run)

        result = await uc(
            ResetRunHitCriteriaCommand(workspace_id=auth.workspace_id, run_id=run.id),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert run.hit_criteria is None
        assert run.hit_criteria_set_by is None
        assert run.hit_criteria_set_at is None
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, _, dispatcher = _build_reset(None)

        result = await uc(
            ResetRunHitCriteriaCommand(workspace_id=auth.workspace_id, run_id=uuid.uuid4()),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        dispatcher.dispatch_all.assert_not_awaited()
