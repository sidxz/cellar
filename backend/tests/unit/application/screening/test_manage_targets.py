"""Unit tests for protocol/run target-link use cases.

Covers the guard paths (404 on missing owner/target, 409 on locked/retired)
and the audit-event emission convention: an event is dispatched only when a
link row actually changed — idempotent no-ops stay silent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.manage_protocol import (
    AddProtocolTarget,
    AddProtocolTargetCommand,
    RemoveProtocolTarget,
    RemoveProtocolTargetCommand,
)
from cellar.application.screening.manage_run_targets import (
    AddRunTarget,
    AddRunTargetCommand,
    RemoveRunTarget,
    RemoveRunTargetCommand,
)
from cellar.domain.screening_assay.events import (
    ProtocolTargetAdded,
    ProtocolTargetRemoved,
    RunTargetAdded,
    RunTargetRemoved,
)
from cellar.domain.screening_assay.repository import TargetLinkResult
from cellar.domain.shared.errors import ConflictError, NotFoundError
from cellar.domain.shared.events import DomainEvent

pytestmark = pytest.mark.asyncio


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
    # Default to the module-level workspace so the require_same_workspace guard
    # matches the WS carried on every command in this module.
    workspace_id: uuid.UUID = field(default_factory=lambda: WS)
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


class FakeDispatcher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.events.extend(events)


def _protocol_uc(
    uc_class: type,
    *,
    lock_state: tuple[bool, str] | None,
    link: TargetLinkResult = TargetLinkResult.ADDED,
    removed: bool = True,
):
    repo = AsyncMock()
    repo.find_lock_state = AsyncMock(return_value=lock_state)
    repo.add_direct_target = AsyncMock(return_value=link)
    repo.remove_direct_target = AsyncMock(return_value=removed)
    uow = FakeUoW()
    dispatcher = FakeDispatcher()
    return uc_class(uow=uow, repo=repo, dispatcher=dispatcher), repo, uow, dispatcher


def _run_uc(
    uc_class: type,
    *,
    lock_state: bool | None,
    link: TargetLinkResult = TargetLinkResult.ADDED,
    removed: bool = True,
):
    repo = AsyncMock()
    repo.find_lock_state = AsyncMock(return_value=lock_state)
    repo.add_target = AsyncMock(return_value=link)
    repo.remove_target = AsyncMock(return_value=removed)
    uow = FakeUoW()
    dispatcher = FakeDispatcher()
    return uc_class(uow=uow, repo=repo, dispatcher=dispatcher), repo, uow, dispatcher


WS = uuid.uuid4()
PID = uuid.uuid4()
RID = uuid.uuid4()
TID = uuid.uuid4()


# ---------------------------------------------------------------------------
# AddProtocolTarget
# ---------------------------------------------------------------------------


class TestAddProtocolTarget:
    async def test_added_emits_audit_event(self) -> None:
        uc, _, uow, dispatcher = _protocol_uc(AddProtocolTarget, lock_state=(False, "draft"))
        auth = FakeAuth(workspace_id=WS)
        result = await uc(
            AddProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=auth,
        )
        assert isinstance(result, Success)
        assert uow.committed
        events = [e for e in dispatcher.events if isinstance(e, ProtocolTargetAdded)]
        assert len(events) == 1
        assert events[0].aggregate_id == PID
        assert events[0].target_id == TID
        assert events[0].user_id == auth.user_id
        assert events[0].workspace_id == WS

    async def test_idempotent_readd_stays_silent(self) -> None:
        uc, _, uow, dispatcher = _protocol_uc(
            AddProtocolTarget,
            lock_state=(False, "active"),
            link=TargetLinkResult.ALREADY_LINKED,
        )
        result = await uc(
            AddProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=FakeAuth(),
        )
        assert isinstance(result, Success)
        assert uow.committed
        assert dispatcher.events == []

    async def test_unknown_target_is_not_found(self) -> None:
        uc, _, uow, dispatcher = _protocol_uc(
            AddProtocolTarget,
            lock_state=(False, "draft"),
            link=TargetLinkResult.TARGET_NOT_FOUND,
        )
        result = await uc(
            AddProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=FakeAuth(),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert not uow.committed
        assert dispatcher.events == []

    async def test_missing_protocol_is_not_found(self) -> None:
        uc, repo, _, _ = _protocol_uc(AddProtocolTarget, lock_state=None)
        result = await uc(
            AddProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=FakeAuth(),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        repo.add_direct_target.assert_not_called()

    async def test_locked_protocol_conflicts(self) -> None:
        uc, repo, _, _ = _protocol_uc(AddProtocolTarget, lock_state=(True, "active"))
        result = await uc(
            AddProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=FakeAuth(),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        repo.add_direct_target.assert_not_called()

    async def test_retired_protocol_conflicts(self) -> None:
        uc, repo, _, _ = _protocol_uc(AddProtocolTarget, lock_state=(False, "retired"))
        result = await uc(
            AddProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=FakeAuth(),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        repo.add_direct_target.assert_not_called()


class TestRemoveProtocolTarget:
    async def test_removed_emits_audit_event(self) -> None:
        uc, _, _, dispatcher = _protocol_uc(RemoveProtocolTarget, lock_state=(False, "active"))
        result = await uc(
            RemoveProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=FakeAuth(),
        )
        assert isinstance(result, Success)
        events = [e for e in dispatcher.events if isinstance(e, ProtocolTargetRemoved)]
        assert len(events) == 1
        assert events[0].target_id == TID

    async def test_not_linked_stays_silent(self) -> None:
        uc, _, _, dispatcher = _protocol_uc(
            RemoveProtocolTarget, lock_state=(False, "active"), removed=False
        )
        result = await uc(
            RemoveProtocolTargetCommand(workspace_id=WS, protocol_id=PID, target_id=TID),
            auth=FakeAuth(),
        )
        assert isinstance(result, Success)
        assert dispatcher.events == []


# ---------------------------------------------------------------------------
# AddRunTarget / RemoveRunTarget
# ---------------------------------------------------------------------------


class TestRunTargets:
    async def test_added_emits_audit_event(self) -> None:
        uc, _, _, dispatcher = _run_uc(AddRunTarget, lock_state=False)
        auth = FakeAuth(workspace_id=WS)
        result = await uc(
            AddRunTargetCommand(workspace_id=WS, run_id=RID, target_id=TID), auth=auth
        )
        assert isinstance(result, Success)
        events = [e for e in dispatcher.events if isinstance(e, RunTargetAdded)]
        assert len(events) == 1
        assert events[0].aggregate_id == RID
        assert events[0].user_id == auth.user_id

    async def test_idempotent_readd_stays_silent(self) -> None:
        uc, _, _, dispatcher = _run_uc(
            AddRunTarget, lock_state=False, link=TargetLinkResult.ALREADY_LINKED
        )
        result = await uc(
            AddRunTargetCommand(workspace_id=WS, run_id=RID, target_id=TID), auth=FakeAuth()
        )
        assert isinstance(result, Success)
        assert dispatcher.events == []

    async def test_unknown_target_is_not_found(self) -> None:
        uc, _, uow, _ = _run_uc(
            AddRunTarget, lock_state=False, link=TargetLinkResult.TARGET_NOT_FOUND
        )
        result = await uc(
            AddRunTargetCommand(workspace_id=WS, run_id=RID, target_id=TID), auth=FakeAuth()
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert not uow.committed

    async def test_missing_run_is_not_found(self) -> None:
        uc, repo, _, _ = _run_uc(AddRunTarget, lock_state=None)
        result = await uc(
            AddRunTargetCommand(workspace_id=WS, run_id=RID, target_id=TID), auth=FakeAuth()
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        repo.add_target.assert_not_called()

    async def test_locked_run_conflicts(self) -> None:
        uc, repo, _, _ = _run_uc(AddRunTarget, lock_state=True)
        result = await uc(
            AddRunTargetCommand(workspace_id=WS, run_id=RID, target_id=TID), auth=FakeAuth()
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        repo.add_target.assert_not_called()

    async def test_remove_emits_event_only_when_removed(self) -> None:
        uc, _, _, dispatcher = _run_uc(RemoveRunTarget, lock_state=False)
        result = await uc(
            RemoveRunTargetCommand(workspace_id=WS, run_id=RID, target_id=TID), auth=FakeAuth()
        )
        assert isinstance(result, Success)
        assert len([e for e in dispatcher.events if isinstance(e, RunTargetRemoved)]) == 1

        uc2, _, _, dispatcher2 = _run_uc(RemoveRunTarget, lock_state=False, removed=False)
        result2 = await uc2(
            RemoveRunTargetCommand(workspace_id=WS, run_id=RID, target_id=TID), auth=FakeAuth()
        )
        assert isinstance(result2, Success)
        assert dispatcher2.events == []
