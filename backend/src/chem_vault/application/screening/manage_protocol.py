"""Protocol management use cases — publish, retire, version."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.protocol import Protocol
from chem_vault.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class PublishProtocol:
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
        self, protocol_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id(protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol"))
            require_same_workspace(auth, protocol.workspace_id)
            protocol.publish()
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)


class RetireProtocol:
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
        protocol_id: uuid.UUID,
        reason: str | None = None,
        auth: AuthContext | None = None,
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id(protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol"))
            require_same_workspace(auth, protocol.workspace_id)
            protocol.retire(reason=reason)
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)


class VersionProtocol:
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
        self, protocol_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id(protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol"))
            require_same_workspace(auth, protocol.workspace_id)

            versioning_service = ProtocolVersioningService()
            new_protocol = versioning_service.create_new_version(protocol)

            # Save both: parent (now retired) and new version
            await self._repo.save(protocol)
            await self._repo.save(new_protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(new_protocol)
