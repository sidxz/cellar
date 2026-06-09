"""Unit tests for the UpdateRun use case — partial (UNSET) field semantics.

Focused on the conditions field added alongside notes/qc_metrics: omitting a
field (UNSET) leaves it untouched, passing a value updates it, and passing
``None`` explicitly clears it.
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

from cellar.application.screening.update_run import UpdateRun, UpdateRunCommand
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.shared.events import DomainEvent

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


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
        run_date=date(2026, 6, 7),
        operator=uuid.uuid4(),
    )
    defaults.update(kwargs)
    return Run.create(**defaults)


def _build_uc(run: Run | None) -> tuple[UpdateRun, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    repo.save = AsyncMock()
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    uc = UpdateRun(uow=FakeUoW(), repo=repo, dispatcher=dispatcher)
    return uc, repo, dispatcher


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpdateRunConditions:
    @pytest.mark.asyncio
    async def test_sets_conditions(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, conditions=None)
        uc, repo, _ = _build_uc(run)

        result = await uc(
            UpdateRunCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                conditions={"Carbon Source": "glucose", "ATP": "10 uM"},
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert run.conditions == {"Carbon Source": "glucose", "ATP": "10 uM"}
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_omitting_conditions_leaves_them_untouched(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, conditions={"pH": "7.4"})
        uc, _, _ = _build_uc(run)

        # Only notes provided; conditions defaults to UNSET and must not change.
        result = await uc(
            UpdateRunCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                notes="touch notes only",
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert run.conditions == {"pH": "7.4"}
        assert run.notes == "touch notes only"

    @pytest.mark.asyncio
    async def test_explicit_none_clears_conditions(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, conditions={"pH": "7.4"})
        uc, _, _ = _build_uc(run)

        result = await uc(
            UpdateRunCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                conditions=None,
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert run.conditions is None

    @pytest.mark.asyncio
    async def test_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, _, dispatcher = _build_uc(None)

        result = await uc(
            UpdateRunCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                conditions={"pH": "7.4"},
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        dispatcher.dispatch_all.assert_not_awaited()
