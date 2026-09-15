"""GetProtocol and ListProtocols query use cases.

Both resolve the protocol's effective target refs inside the SAME unit of
work as the primary read, so a response never mixes two snapshots (the
``list_protocol_summaries`` precedent).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import ProtocolStatus
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetProtocolQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListProtocolsQuery(Query):
    workspace_id: uuid.UUID
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"


@dataclass(frozen=True)
class ProtocolWithTargets:
    """A protocol plus its effective target refs, read in one transaction."""

    protocol: Protocol
    targets: list[TargetRef] = field(default_factory=list)
    #: Whether the caller could delete it right now. Only GetProtocol fills it;
    #: None elsewhere means "not computed", not "no".
    can_delete: bool | None = None


def may_delete_protocol(protocol: Protocol, auth: AuthContext | None) -> bool:
    """Drafts only, by their creator or an admin. Says nothing about usages."""
    if protocol.status != ProtocolStatus.DRAFT:
        return False
    return auth is None or auth.has_role("admin") or protocol.created_by == auth.user_id


class GetProtocol:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetProtocolQuery, auth: AuthContext | None = None
    ) -> Result[ProtocolWithTargets, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            targets = await self._repo.find_effective_targets_for_protocols(
                input.workspace_id, [protocol.id]
            )
            can_delete = (auth is None or auth.has_role("editor")) and may_delete_protocol(
                protocol, auth
            )
            if can_delete:
                can_delete = not await self._repo.find_usages(input.workspace_id, protocol.id)
            return Success(
                ProtocolWithTargets(
                    protocol=protocol,
                    targets=targets.get(protocol.id, []),
                    can_delete=can_delete,
                )
            )


class ListProtocols:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProtocolsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[ProtocolWithTargets], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            protocols = await self._repo.find_by_workspace(
                input.workspace_id,
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
