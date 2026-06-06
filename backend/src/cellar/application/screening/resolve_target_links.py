"""Read-side queries that resolve target links for API responses.

- ``GetProtocolTargets`` — rich effective targets (with is_direct / run_count)
  for a single protocol's design tab.
- ``ResolveProtocolTargets`` — batched lightweight target refs per protocol for
  the protocol grid / detail header.
- ``ResolveRunTargets`` — batched lightweight target refs per run for the run
  grid / run detail card.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import ProtocolRepository, RunRepository
from cellar.domain.screening_assay.target import EffectiveTarget, TargetRef
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetProtocolTargetsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ResolveProtocolTargetsQuery(Query):
    workspace_id: uuid.UUID
    protocol_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, kw_only=True)
class ResolveRunTargetsQuery(Query):
    workspace_id: uuid.UUID
    run_ids: tuple[uuid.UUID, ...]


class GetProtocolTargets:
    """Rich effective-target list for a single protocol (design tab)."""

    def __init__(self, uow: UnitOfWork, protocol_repo: ProtocolRepository) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo

    async def __call__(
        self, input: GetProtocolTargetsQuery, auth: AuthContext | None = None
    ) -> Result[list[EffectiveTarget], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            # Ownership check first: a foreign/missing protocol must 404 like
            # every sibling GET-by-id, not return 200 [].
            state = await self._protocol_repo.find_lock_state(
                input.workspace_id, input.protocol_id
            )
            if state is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            targets = await self._protocol_repo.find_effective_targets(
                input.workspace_id, input.protocol_id
            )
        return Success(targets)


class ResolveProtocolTargets:
    """Batched lightweight target refs keyed by protocol id."""

    def __init__(self, uow: UnitOfWork, protocol_repo: ProtocolRepository) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo

    async def __call__(
        self, input: ResolveProtocolTargetsQuery, auth: AuthContext | None = None
    ) -> Result[dict[uuid.UUID, list[TargetRef]], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            result = await self._protocol_repo.find_effective_targets_for_protocols(
                input.workspace_id, list(input.protocol_ids)
            )
        return Success(result)


class ResolveRunTargets:
    """Batched lightweight target refs keyed by run id."""

    def __init__(self, uow: UnitOfWork, run_repo: RunRepository) -> None:
        self._uow = uow
        self._run_repo = run_repo

    async def __call__(
        self, input: ResolveRunTargetsQuery, auth: AuthContext | None = None
    ) -> Result[dict[uuid.UUID, list[TargetRef]], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            result = await self._run_repo.find_target_refs_for_runs(
                input.workspace_id, list(input.run_ids)
            )
        return Success(result)
