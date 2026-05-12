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
    def __init__(self, stats: dict[uuid.UUID, ProjectScopeStats]) -> None:
        self._stats = stats
        self.calls: list[tuple[uuid.UUID, list[uuid.UUID]]] = []

    async def get_scope_stats(
        self, workspace_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ProjectScopeStats]:
        self.calls.append((workspace_id, list(project_ids)))
        return {pid: self._stats[pid] for pid in project_ids if pid in self._stats}


@pytest.mark.asyncio
async def test_returns_stats_for_known_projects() -> None:
    ws = uuid.uuid4()
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    repo = FakeProjectRepo(
        {
            p1: ProjectScopeStats(molecule_count=10, protocol_count=2, run_count=5),
            p2: ProjectScopeStats(molecule_count=0, protocol_count=0, run_count=0),
        }
    )
    use_case = GetProjectScopeStats(FakeUnitOfWork(), repo)  # type: ignore[arg-type]

    result = await use_case(
        GetProjectScopeStatsQuery(workspace_id=ws, project_ids=(p1, p2))
    )

    assert isinstance(result, Success)
    stats = result.unwrap()
    assert stats[p1].molecule_count == 10
    assert stats[p1].protocol_count == 2
    assert stats[p1].run_count == 5
    assert stats[p2].molecule_count == 0
    assert repo.calls == [(ws, [p1, p2])]


@pytest.mark.asyncio
async def test_empty_project_ids_short_circuits() -> None:
    repo = FakeProjectRepo({})
    use_case = GetProjectScopeStats(FakeUnitOfWork(), repo)  # type: ignore[arg-type]

    result = await use_case(
        GetProjectScopeStatsQuery(workspace_id=uuid.uuid4(), project_ids=())
    )

    assert isinstance(result, Success)
    assert result.unwrap() == {}
    assert repo.calls == []  # repo never hit when no IDs given


@pytest.mark.asyncio
async def test_unknown_project_id_omitted_from_response() -> None:
    ws = uuid.uuid4()
    p_known = uuid.uuid4()
    p_missing = uuid.uuid4()
    repo = FakeProjectRepo(
        {p_known: ProjectScopeStats(molecule_count=1, protocol_count=1, run_count=1)}
    )
    use_case = GetProjectScopeStats(FakeUnitOfWork(), repo)  # type: ignore[arg-type]

    result = await use_case(
        GetProjectScopeStatsQuery(workspace_id=ws, project_ids=(p_known, p_missing))
    )

    stats = result.unwrap()
    assert p_known in stats
    assert p_missing not in stats
