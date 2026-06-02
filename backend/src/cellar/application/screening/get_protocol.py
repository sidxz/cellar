"""GetProtocol and ListProtocols query use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository
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


class GetProtocol:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetProtocolQuery, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            return Success(protocol)


class ListProtocols:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProtocolsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Protocol], DomainError]:
        require_workspace_role(auth, "viewer")
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

            return Success(PageResult(items=protocols, next_cursor=next_cursor))
