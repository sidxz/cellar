"""Protocol management use cases — publish, retire, version, update, delete."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_admin, require_editor, require_same_workspace
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import ProtocolStatus
from chem_vault.domain.screening_assay.protocol import Protocol
from chem_vault.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError


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

            # If this protocol is a new version, retire the parent
            if protocol.parent_protocol_id is not None:
                parent = await self._repo.find_by_id(protocol.parent_protocol_id)
                if parent is not None and parent.status == ProtocolStatus.ACTIVE:
                    parent.retire(reason=f"Superseded by version {protocol.protocol_version}")
                    await self._repo.save(parent)

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

            # Save only the new draft — parent stays ACTIVE until new version is published
            await self._repo.save(new_protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(new_protocol)


@dataclass(frozen=True, kw_only=True)
class UpdateProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    name: str | None = None
    description: str | None | object = UNSET
    target_id: uuid.UUID | None | object = UNSET
    category: str | None | object = UNSET


class UpdateProtocol:
    """Update a DRAFT protocol's metadata fields."""

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
        self, input: UpdateProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id(input.protocol_id)
            if protocol is None or protocol.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            fields: dict[str, object] = {}
            if input.name is not None:
                fields["name"] = input.name
            if input.description is not UNSET:
                fields["description"] = input.description
            if input.target_id is not UNSET:
                fields["target_id"] = input.target_id
            if input.category is not UNSET:
                fields["category"] = input.category

            if fields:
                protocol.update(**fields)  # Guards: only DRAFT allowed
            await self._repo.save(protocol)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(protocol)


class DeleteProtocol:
    """Delete a DRAFT protocol. Only drafts can be deleted."""

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
    ) -> Result[None, DomainError]:
        require_admin(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id(protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(protocol_id)))

            if protocol.status != ProtocolStatus.DRAFT:
                return Failure(
                    ConflictError(f"Cannot delete protocol in '{protocol.status}' status — only DRAFT protocols can be deleted")
                )

            await self._repo.delete(protocol_id)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(None)
