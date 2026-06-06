"""Protocol locking use cases — lock and unlock.

Mirrors lock_run.py. The lock is a workflow gate orthogonal to the
DRAFT/ACTIVE/RETIRED status — used during regulatory submissions or
cross-team coordination to freeze the protocol metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class LockProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class UnlockProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    reason: str


class LockProtocol:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: LockProtocolCommand,
        auth: AuthContext | None = None,
    ) -> Result[Protocol, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            protocol.lock(locked_by=auth.user_id, reason=input.reason)
            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


class UnlockProtocol:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: UnlockProtocolCommand,
        auth: AuthContext | None = None,
    ) -> Result[Protocol, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            protocol.unlock(unlocked_by=auth.user_id, reason=input.reason)
            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
