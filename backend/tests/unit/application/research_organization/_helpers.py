"""Shared test helpers for campaign use-case unit tests.

These are intentionally not shipped as fixtures — they are plain callables that
every test file can import and compose freely.
"""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Callable, Self
from unittest.mock import AsyncMock

from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.shared.events import DomainEvent


# ---------------------------------------------------------------------------
# FakeUnitOfWork
# ---------------------------------------------------------------------------


class _FakeSession:
    """Minimal fake session that provides a no-op flush() for use cases that need it.

    The ``execute`` method returns whatever is set on ``_execute_result``.
    Set ``session._execute_result = your_mock_result`` before calling a use
    case that does SQL queries (e.g. AddResultsFromRun).
    """

    def __init__(self) -> None:
        self._execute_result = AsyncMock()

    async def flush(self) -> None:
        pass

    async def execute(self, stmt) -> AsyncMock:
        return self._execute_result


class FakeUnitOfWork:
    """Minimal async-context-manager UoW that collects and clears domain events."""

    def __init__(self) -> None:
        self._tracked: list = []
        self.session = _FakeSession()

    @property
    def is_active(self) -> bool:
        return True

    def track(self, aggregate) -> None:
        if aggregate not in self._tracked:
            self._tracked.append(aggregate)

    async def commit(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for agg in self._tracked:
            events.extend(agg.collect_events())
            agg.clear_events()
        return events

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
        pass


# ---------------------------------------------------------------------------
# fake_auth
# ---------------------------------------------------------------------------


def fake_auth(*, role: str = "editor", is_admin: bool = False):
    """Return an AsyncMock auth object with role-hierarchy support."""
    auth = AsyncMock()
    auth.user_id = uuid.uuid4()
    auth.workspace_id = uuid.uuid4()
    auth.workspace_role = role
    auth.is_admin = is_admin
    # role hierarchy: viewer < editor < admin
    rank = {"viewer": 0, "editor": 1, "admin": 2}
    current = rank.get(role, 0)
    auth.has_role = lambda min_role: current >= rank.get(min_role, 0)
    return auth


# ---------------------------------------------------------------------------
# make_campaign_repo
# ---------------------------------------------------------------------------


def make_campaign_repo(
    saved: list[Campaign] | None = None,
    *,
    find_in_ws: Campaign | None = None,
    find_dispatch: dict[uuid.UUID, Campaign | None] | None = None,
) -> AsyncMock:
    """Return an AsyncMock campaign repository.

    Args:
        saved: If provided, the mock's ``save`` side-effect appends to this
            list and exposes it as ``repo.saved``.  Useful when callers want
            to inspect what was persisted.
        find_in_ws: Returned by ``find_by_id_in_workspace`` for any call when
            ``find_dispatch`` is not given.
        find_dispatch: When provided, ``find_by_id_in_workspace`` looks up its
            second argument (the campaign id) in this mapping; returns ``None``
            on a miss.  Takes priority over ``find_in_ws``.
    """
    repo = AsyncMock()
    captured: list[Campaign] = saved if saved is not None else []

    async def _save(agg: Campaign) -> None:
        captured.append(agg)

    repo.save = AsyncMock(side_effect=_save)
    repo.saved = captured  # type: ignore[attr-defined]

    if find_dispatch is not None:
        async def _find(ws_id: uuid.UUID, camp_id: uuid.UUID) -> Campaign | None:
            return find_dispatch.get(camp_id)

        repo.find_by_id_in_workspace = AsyncMock(side_effect=_find)
    else:
        repo.find_by_id_in_workspace = AsyncMock(return_value=find_in_ws)

    return repo


# ---------------------------------------------------------------------------
# make_collection_repo
# ---------------------------------------------------------------------------


def make_collection_repo(
    *,
    in_ws: bool = True,
    molecule_ids: list[uuid.UUID] | None = None,
) -> AsyncMock:
    """Return an AsyncMock collection repository."""
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(
        return_value=object() if in_ws else None
    )
    repo.get_molecule_ids = AsyncMock(return_value=molecule_ids or [])
    return repo


# ---------------------------------------------------------------------------
# FakeResolver
# ---------------------------------------------------------------------------


class FakeResolver:
    """Async channel resolver that delegates measurement construction to a factory.

    Args:
        factory: Callable ``(channel, result_id, molecule_id) -> CampaignMeasurement``.
            Required — callers must supply an appropriate factory for their test.
    """

    def __init__(self, factory: Callable) -> None:
        self._factory = factory
        self.calls: list = []

    async def resolve(self, *, workspace_id, channel, result_id, molecule_id):
        self.calls.append((channel.id, result_id, molecule_id))
        return self._factory(channel, result_id, molecule_id)
