"""Unit tests for GetProjectScopeStats use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Success

from cellar.application.research_organization.get_project_scope_stats import (
    GetProjectScopeStats,
    GetProjectScopeStatsQuery,
)
from cellar.domain.research_organization.project_scope_stats import ProjectScopeStats


class FakeUnitOfWork:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    def track(self, _aggregate) -> None:
        pass

    async def commit(self):  # pragma: no cover — read path doesn't commit
        return []

    async def rollback(self) -> None:
        pass


class FakeProjectRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    async def get_scope_stats(
        self, workspace_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ProjectScopeStats]:
        self.calls.append((workspace_id, list(project_ids)))
        return {}


@pytest.mark.asyncio
async def test_forwards_workspace_and_project_ids_to_repo() -> None:
    ws = uuid.uuid4()
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    repo = FakeProjectRepo()
    use_case = GetProjectScopeStats(FakeUnitOfWork(), repo)  # type: ignore[arg-type]

    result = await use_case(GetProjectScopeStatsQuery(workspace_id=ws, project_ids=(p1, p2)))

    assert isinstance(result, Success)
    assert repo.calls == [(ws, [p1, p2])]


@pytest.mark.asyncio
async def test_empty_project_ids_short_circuits() -> None:
    repo = FakeProjectRepo()
    use_case = GetProjectScopeStats(FakeUnitOfWork(), repo)  # type: ignore[arg-type]

    result = await use_case(
        GetProjectScopeStatsQuery(workspace_id=uuid.uuid4(), project_ids=())
    )

    assert isinstance(result, Success)
    assert result.unwrap() == {}
    assert repo.calls == []  # repo never hit when no IDs given
