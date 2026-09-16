"""GetTarget and ListTargets query use cases."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.sync_targets import SyncTargetsCommand, SyncTargetsFromProtCellar
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import DomainError, NotFoundError

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class GetTargetQuery(Query):
    workspace_id: uuid.UUID
    target_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListTargetsQuery(Query):
    workspace_id: uuid.UUID
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    # The caller's Duar headers, forwarded to prot-cellar for the best-effort
    # mirror refresh. Empty (e.g. FakeAuth in tests) = skip the refresh.
    forwarded_headers: Mapping[str, str] = field(default_factory=dict)


class GetTarget:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetTargetQuery, auth: AuthContext | None = None
    ) -> Result[Target, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            target = await self._repo.find_by_id_in_workspace(input.workspace_id, input.target_id)
            if target is None:
                return Failure(NotFoundError("Target", str(input.target_id)))
            return Success(target)


class ListTargets:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: TargetRepository,
        sync: SyncTargetsFromProtCellar | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._sync = sync

    async def __call__(
        self, input: ListTargetsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Target], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        # Best-effort: a stale mirror is served rather than failing the list.
        # The sync use case logs the reason; viewers hitting prot-cellar's
        # editor requirement land here on every TTL lapse — expected.
        if self._sync is not None and input.forwarded_headers:
            await self._sync(
                SyncTargetsCommand(
                    workspace_id=input.workspace_id,
                    forwarded_headers=input.forwarded_headers,
                    force=False,
                ),
                auth=auth,
            )

        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            targets = await self._repo.find_by_workspace(
                input.workspace_id,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(targets) > effective_limit:
                targets = targets[:effective_limit]
                next_cursor = str(targets[-1].id)

            return Success(PageResult(items=targets, next_cursor=next_cursor))
