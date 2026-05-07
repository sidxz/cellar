"""Protocol management use cases — publish, retire, version, update, delete."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_admin, require_editor, require_same_workspace
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import PosControlSignal, ProtocolStatus
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.domain.screening_assay.protocol import Protocol
from chem_vault.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class PublishProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RetireProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class VersionProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


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
        self, input: PublishProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            protocol.publish()

            # If this protocol is a new version, retire the parent
            if protocol.parent_protocol_id is not None:
                parent = await self._repo.find_by_id_in_workspace(protocol.workspace_id, protocol.parent_protocol_id)
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
        self, input: RetireProtocolCommand, auth: AuthContext | None = None,
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            protocol.retire(reason=input.reason)
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
        self, input: VersionProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

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
    recommended_hit_criteria: list[dict] | None | object = UNSET
    pos_control_signal: str | None = None


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
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            fields: dict[str, Any] = {}
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

            if input.recommended_hit_criteria is not UNSET:
                criteria = None
                if input.recommended_hit_criteria is not None:
                    criteria = [HitCriterion.from_dict(c) for c in input.recommended_hit_criteria]
                protocol.set_recommended_hit_criteria(criteria)

            # pos_control_signal uses its own setter — allowed on ACTIVE
            # protocols too (the ``update()`` path above is DRAFT-only).
            if input.pos_control_signal is not None:
                protocol.set_pos_control_signal(
                    PosControlSignal(input.pos_control_signal)
                )

            await self._repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


@dataclass(frozen=True, kw_only=True)
class DeleteProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListProtocolsByProjectQuery(Query):
    workspace_id: uuid.UUID
    project_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class AddProtocolToProjectCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    project_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveProtocolFromProjectCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    project_id: uuid.UUID


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
        self, input: DeleteProtocolCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            if protocol.status != ProtocolStatus.DRAFT:
                return Failure(
                    ConflictError(f"Cannot delete protocol in '{protocol.status}' status — only DRAFT protocols can be deleted")
                )

            await self._repo.delete(protocol.workspace_id, input.protocol_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListProtocolsByProject:
    """List protocols linked to a project."""

    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListProtocolsByProjectQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[Protocol], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocols = await self._repo.find_by_project(input.workspace_id, input.project_id)
            return Success(protocols)


class AddProtocolToProject:
    """Link a protocol to a project (idempotent)."""

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
        input: AddProtocolToProjectCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            await self._repo.add_to_project(input.workspace_id, input.protocol_id, input.project_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemoveProtocolFromProject:
    """Unlink a protocol from a project."""

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
        input: RemoveProtocolFromProjectCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            await self._repo.remove_from_project(input.workspace_id, input.protocol_id, input.project_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
