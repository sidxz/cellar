"""Read use cases for collection coverage: per-run resolution + protocol rollup.

``ResolveRunCollections`` populates the ``collections`` field on run responses
(single-run GET and list). ``GetProtocolCollectionCoverage`` powers the protocol
rollup, with the same ownership-first 404 discipline as ``GetProtocolTargets``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    EffectiveCollectionCoverage,
)
from cellar.domain.screening_assay.repository import (
    CollectionCoverageReader,
    ProtocolRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ResolveRunCollectionsQuery(Query):
    workspace_id: uuid.UUID
    run_ids: tuple[uuid.UUID, ...]


class ResolveRunCollections:
    """Coverage per attached collection for the given runs."""

    def __init__(self, uow: UnitOfWork, reader: CollectionCoverageReader) -> None:
        self._uow = uow
        self._reader = reader

    async def __call__(
        self, input: ResolveRunCollectionsQuery, auth: AuthContext | None = None
    ) -> Result[dict[uuid.UUID, list[CollectionCoverage]], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            data = await self._reader.run_coverage(input.workspace_id, list(input.run_ids))
        return Success(data)


@dataclass(frozen=True, kw_only=True)
class GetProtocolCollectionCoverageQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


class GetProtocolCollectionCoverage:
    """Cumulative coverage per collection across a protocol's attaching runs."""

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
        self, input: GetProtocolCollectionCoverageQuery, auth: AuthContext | None = None
    ) -> Result[list[EffectiveCollectionCoverage], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            # Ownership check first: a foreign/missing protocol must 404 like
            # every sibling GET-by-id, not return 200 [].
            state = await self._protocol_repo.find_lock_state(
                input.workspace_id, input.protocol_id
            )
            if state is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            rollup = await self._reader.protocol_coverage(input.workspace_id, input.protocol_id)
        return Success(rollup)
