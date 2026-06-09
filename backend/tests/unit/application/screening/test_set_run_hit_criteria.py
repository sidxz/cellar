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
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError, NotFoundError
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


def _build_set(run: Run | None) -> tuple[SetRunHitCriteria, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    repo.save = AsyncMock()
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    return SetRunHitCriteria(uow=FakeUoW(), repo=repo, dispatcher=dispatcher), repo, dispatcher


def _build_reset(run: Run | None) -> tuple[ResetRunHitCriteria, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    repo.save = AsyncMock()
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    return ResetRunHitCriteria(uow=FakeUoW(), repo=repo, dispatcher=dispatcher), repo, dispatcher


class TestSetRunHitCriteria:
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
