"""Protocol management use cases — publish, retire, version, update, delete."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin,
    require_editor,
    require_same_workspace,
)
from cellar.application.screening.get_protocol import ProtocolWithTargets
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import PosControlSignal, ProtocolStatus
from cellar.domain.screening_assay.events import ProtocolTargetAdded, ProtocolTargetRemoved
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from cellar.domain.screening_assay.repository import ProtocolRepository, TargetLinkResult
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError
from cellar.domain.shared.hit_criterion import HitCriterion


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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            protocol.publish()

            # If this protocol is a new version, retire the parent
            if protocol.parent_protocol_id is not None:
                parent = await self._repo.find_by_id_in_workspace(
                    protocol.workspace_id, protocol.parent_protocol_id
                )
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
        input: RetireProtocolCommand,
        auth: AuthContext | None = None,
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            versioning_service = ProtocolVersioningService()
            new_protocol = versioning_service.create_new_version(protocol)

            # Save only the new draft — parent stays ACTIVE until new version is published
            await self._repo.save(new_protocol)
            # Carry forward the parent's DIRECT targets. Inherited targets are
            # not copied — they re-derive from the new version's own runs.
            direct_ids = await self._repo.find_direct_target_ids(input.workspace_id, protocol.id)
            for target_id in direct_ids:
                await self._repo.add_direct_target(input.workspace_id, new_protocol.id, target_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(new_protocol)


@dataclass(frozen=True, kw_only=True)
class UpdateProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    name: str | None = None
    description: str | object | None = UNSET
    category: str | object | None = UNSET
    recommended_hit_criteria: list[dict] | object | None = UNSET
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            fields: dict[str, Any] = {}
            if input.name is not None:
                fields["name"] = input.name
            if input.description is not UNSET:
                fields["description"] = input.description
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
                protocol.set_pos_control_signal(PosControlSignal(input.pos_control_signal))

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
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"


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


@dataclass(frozen=True, kw_only=True)
class AddProtocolTargetCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    target_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveProtocolTargetCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    target_id: uuid.UUID


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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            if protocol.status != ProtocolStatus.DRAFT:
                return Failure(
                    ConflictError(
                        f"Cannot delete protocol in '{protocol.status}' status — "
                        "only DRAFT protocols can be deleted"
                    )
                )

            await self._repo.delete(protocol.workspace_id, input.protocol_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListProtocolsByProject:
    """List protocols linked to a project (targets resolved in the same UoW)."""

    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListProtocolsByProjectQuery,
        auth: AuthContext | None = None,
    ) -> Result[PageResult[ProtocolWithTargets], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            protocols = await self._repo.find_by_project(
                input.workspace_id,
                input.project_id,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
                tags=input.tags,
                tag_logic=input.tag_logic,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(protocols) > effective_limit:
                protocols = protocols[:effective_limit]
                next_cursor = str(protocols[-1].id)

            targets = await self._repo.find_effective_targets_for_protocols(
                input.workspace_id, [p.id for p in protocols]
            )
            return Success(
                PageResult(
                    items=[
                        ProtocolWithTargets(protocol=p, targets=targets.get(p.id, []))
                        for p in protocols
                    ],
                    next_cursor=next_cursor,
                )
            )


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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            await self._repo.add_to_project(
                input.workspace_id, input.protocol_id, input.project_id
            )
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            await self._repo.remove_from_project(
                input.workspace_id, input.protocol_id, input.project_id
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class AddProtocolTarget:
    """Attach a direct target to a protocol (idempotent).

    Targets are an M2M association (not aggregate state), so the lock/status
    guard uses a column-only query and the audit event is constructed here
    rather than registered on the aggregate. No version bump: idempotent
    association edits must not trigger optimistic-concurrency conflicts.
    """

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
        self, input: AddProtocolTargetCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            state = await self._repo.find_lock_state(input.workspace_id, input.protocol_id)
            if state is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            is_locked, status = state
            if is_locked:
                return Failure(ConflictError("Protocol is locked — unlock to change targets"))
            if status == ProtocolStatus.RETIRED.value:
                return Failure(ConflictError("Cannot change targets on a retired protocol"))
            link = await self._repo.add_direct_target(
                input.workspace_id, input.protocol_id, input.target_id
            )
            if link is TargetLinkResult.TARGET_NOT_FOUND:
                return Failure(NotFoundError("Target", str(input.target_id)))
            if link is TargetLinkResult.OWNER_NOT_FOUND:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            events = await self._uow.commit()

        if link is TargetLinkResult.ADDED:
            events.append(
                ProtocolTargetAdded(
                    aggregate_id=input.protocol_id,
                    aggregate_type="Protocol",
                    workspace_id=input.workspace_id,
                    target_id=input.target_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemoveProtocolTarget:
    """Remove a direct target from a protocol. See ``AddProtocolTarget`` for
    the guard/event conventions."""

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
        self, input: RemoveProtocolTargetCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            state = await self._repo.find_lock_state(input.workspace_id, input.protocol_id)
            if state is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            is_locked, status = state
            if is_locked:
                return Failure(ConflictError("Protocol is locked — unlock to change targets"))
            if status == ProtocolStatus.RETIRED.value:
                return Failure(ConflictError("Cannot change targets on a retired protocol"))
            removed = await self._repo.remove_direct_target(
                input.workspace_id, input.protocol_id, input.target_id
            )
            events = await self._uow.commit()

        if removed:
            events.append(
                ProtocolTargetRemoved(
                    aggregate_id=input.protocol_id,
                    aggregate_type="Protocol",
                    workspace_id=input.workspace_id,
                    target_id=input.target_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)
