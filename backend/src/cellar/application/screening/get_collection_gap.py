"""Gap use cases: collection members not yet screened (run-level + protocol)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import (
    CollectionCoverageReader,
    ProtocolRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetRunCollectionGapQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    collection_id: uuid.UUID
    offset: int = 0
    limit: int = 100


class GetRunCollectionGap:
    """Collection molecules a single run has not yet screened (paged)."""

    def __init__(
        self, uow: UnitOfWork, run_repo: RunRepository, reader: CollectionCoverageReader
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._reader = reader

    async def __call__(
        self, input: GetRunCollectionGapQuery, auth: AuthContext | None = None
    ) -> Result[list[uuid.UUID], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            state = await self._run_repo.find_lock_state(input.workspace_id, input.run_id)
            if state is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            ids = await self._reader.run_gap(
                input.workspace_id,
                input.run_id,
                input.collection_id,
                offset=input.offset,
                limit=input.limit,
            )
        return Success(ids)


@dataclass(frozen=True, kw_only=True)
class GetProtocolCollectionGapQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    collection_id: uuid.UUID
    offset: int = 0
    limit: int = 100


class GetProtocolCollectionGap:
    """Collection molecules no run of the protocol has screened (paged)."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        reader: CollectionCoverageReader,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._reader = reader

    async def __call__(
        self, input: GetProtocolCollectionGapQuery, auth: AuthContext | None = None
    ) -> Result[list[uuid.UUID], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            state = await self._protocol_repo.find_lock_state(
                input.workspace_id, input.protocol_id
            )
            if state is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            ids = await self._reader.protocol_gap(
                input.workspace_id,
                input.protocol_id,
                input.collection_id,
                offset=input.offset,
                limit=input.limit,
            )
        return Success(ids)
