"""Tests for ListProtocolSummaries use case (rich protocol picker)."""

from __future__ import annotations

import uuid
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from chem_vault.application.screening.list_protocol_summaries import (
    ListProtocolSummaries,
    ListProtocolSummariesQuery,
    ProtocolSummary,
)
from chem_vault.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth


WS = uuid.uuid4()
P_A = uuid.uuid4()
P_B = uuid.uuid4()
P_C = uuid.uuid4()
T_NADD = uuid.uuid4()


class _FakeUoW:
    async def commit(self) -> list[DomainEvent]:
        return []

    async def rollback(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class _FakeProtocol:
    def __init__(
        self,
        *,
        id: uuid.UUID,
        name: str,
        status: str = "active",
        target_id: uuid.UUID | None = None,
        protocol_type: str = "dose_response",
        description: str | None = None,
    ) -> None:
        self.id = id
        self.name = name
        # Simulate the .value-bearing enum on the real aggregate
        self.status = type("S", (), {"value": status})()
        self.target_id = target_id
        self.protocol_type = type("PT", (), {"value": protocol_type})()
        self.description = description


class _FakeTarget:
    def __init__(self, *, id: uuid.UUID, name: str) -> None:
        self.id = id
        self.name = name


@pytest.mark.asyncio
async def test_list_protocol_summaries_merges_run_stats() -> None:
    """Each summary carries run_count + last_run_date computed by repo."""
    proto_repo = AsyncMock()
    proto_repo.find_by_workspace.return_value = [
        _FakeProtocol(id=P_A, name="NadD-Sumo DR", target_id=T_NADD),
        _FakeProtocol(id=P_B, name="NadD-Sumo single-point"),
        _FakeProtocol(id=P_C, name="MtbNadD biochem", status="archived"),
    ]
    target_repo = AsyncMock()
    target_repo.find_by_workspace.return_value = [
        _FakeTarget(id=T_NADD, name="NadD"),
    ]
    run_repo = AsyncMock()
    run_repo.aggregate_stats_by_protocol.return_value = {
        P_A: (142, date(2026, 4, 20)),
        P_B: (38, date(2025, 11, 4)),
        # P_C has no runs
    }

    uc = ListProtocolSummaries(
        uow=_FakeUoW(),
        protocol_repo=proto_repo,
        target_repo=target_repo,
        run_repo=run_repo,
    )
    result = await uc(
        ListProtocolSummariesQuery(workspace_id=WS),
        auth=FakeAuth(workspace_id=WS),
    )

    assert isinstance(result, Success)
    summaries: list[ProtocolSummary] = result.unwrap()

    by_id = {s.id: s for s in summaries}
    assert by_id[P_A].run_count == 142
    assert by_id[P_A].last_run_date == date(2026, 4, 20)
    assert by_id[P_A].target_id == T_NADD
    assert by_id[P_A].target_name == "NadD"

    assert by_id[P_B].run_count == 38
    assert by_id[P_B].last_run_date == date(2025, 11, 4)
    assert by_id[P_B].target_name is None  # no target_id

    # Protocol with no runs: count = 0, last_run_date = None
    assert by_id[P_C].run_count == 0
    assert by_id[P_C].last_run_date is None
    assert by_id[P_C].status == "archived"


@pytest.mark.asyncio
async def test_list_protocol_summaries_scopes_to_projects_union() -> None:
    """When project_ids is given, only protocols linked to those projects appear.

    Mirrors the search-panel picker behaviour: chemists scoped to "Anti-inflammatory"
    + "Oncology" should see protocols in either, never the workspace-wide noise.
    """
    proto_repo = AsyncMock()
    proto_repo.find_by_workspace.return_value = [
        _FakeProtocol(id=P_A, name="In project A"),
        _FakeProtocol(id=P_B, name="In project B"),
        _FakeProtocol(id=P_C, name="In neither (excluded)"),
    ]
    target_repo = AsyncMock()
    target_repo.find_by_workspace.return_value = []
    run_repo = AsyncMock()
    run_repo.aggregate_stats_by_protocol.return_value = {}
    proto_repo.find_protocol_ids_in_projects.return_value = {P_A, P_B}

    proj_a = uuid.uuid4()
    proj_b = uuid.uuid4()

    uc = ListProtocolSummaries(
        uow=_FakeUoW(),
        protocol_repo=proto_repo,
        target_repo=target_repo,
        run_repo=run_repo,
    )
    result = await uc(
        ListProtocolSummariesQuery(workspace_id=WS, project_ids=(proj_a, proj_b)),
        auth=FakeAuth(workspace_id=WS),
    )
    summaries = result.unwrap()
    ids = {s.id for s in summaries}
    assert ids == {P_A, P_B}
    proto_repo.find_protocol_ids_in_projects.assert_awaited_once_with(
        WS, [proj_a, proj_b]
    )


@pytest.mark.asyncio
async def test_list_protocol_summaries_unscoped_skips_project_lookup() -> None:
    """Workspace-wide list (no project_ids) must NOT touch the project repo."""
    proto_repo = AsyncMock()
    proto_repo.find_by_workspace.return_value = [
        _FakeProtocol(id=P_A, name="anything"),
    ]
    target_repo = AsyncMock()
    target_repo.find_by_workspace.return_value = []
    run_repo = AsyncMock()
    run_repo.aggregate_stats_by_protocol.return_value = {}

    uc = ListProtocolSummaries(
        uow=_FakeUoW(),
        protocol_repo=proto_repo,
        target_repo=target_repo,
        run_repo=run_repo,
    )
    result = await uc(
        ListProtocolSummariesQuery(workspace_id=WS),
        auth=FakeAuth(workspace_id=WS),
    )
    assert {s.id for s in result.unwrap()} == {P_A}
    proto_repo.find_protocol_ids_in_projects.assert_not_called()


@pytest.mark.asyncio
async def test_list_protocol_summaries_orders_by_last_run_desc() -> None:
    """Protocols with recent runs come before stale ones; never-run last."""
    proto_repo = AsyncMock()
    proto_repo.find_by_workspace.return_value = [
        _FakeProtocol(id=P_C, name="oldest"),
        _FakeProtocol(id=P_A, name="newest"),
        _FakeProtocol(id=P_B, name="never-run"),
    ]
    target_repo = AsyncMock()
    target_repo.find_by_workspace.return_value = []
    run_repo = AsyncMock()
    run_repo.aggregate_stats_by_protocol.return_value = {
        P_A: (5, date(2026, 4, 20)),
        P_C: (12, date(2024, 1, 1)),
    }

    uc = ListProtocolSummaries(
        uow=_FakeUoW(),
        protocol_repo=proto_repo,
        target_repo=target_repo,
        run_repo=run_repo,
    )
    result = await uc(
        ListProtocolSummariesQuery(workspace_id=WS),
        auth=FakeAuth(workspace_id=WS),
    )

    summaries = result.unwrap()
    ids_in_order = [s.id for s in summaries]
    assert ids_in_order == [P_A, P_C, P_B]
