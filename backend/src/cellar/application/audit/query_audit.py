"""Audit query use cases — read-only access to audit trail.

These use cases operate directly on the AuditRepository (no UoW needed)
because the audit repository manages its own session (append-only,
no transactional mutations).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.domain.audit_compliance.models import AuditOperation
from cellar.domain.audit_compliance.repository import AuditRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListAuditOperationsQuery(Query):
    workspace_id: uuid.UUID
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    cursor_id: uuid.UUID | None = None
    limit: int | None = None


class ListAuditOperations:
    """List audit operations with optional filters."""

    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: ListAuditOperationsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[AuditOperation], DomainError]:
        require_workspace_role(auth, "viewer")
        effective_limit = input.limit
        fetch_limit = effective_limit + 1 if effective_limit is not None else None
        operations = await self._repo.find_all(
            input.workspace_id,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            user_id=input.user_id,
            cursor_id=input.cursor_id,
            limit=fetch_limit,
        )

        next_cursor: str | None = None
        if effective_limit is not None and len(operations) > effective_limit:
            operations = operations[:effective_limit]
            next_cursor = str(operations[-1].id)

        return Success(PageResult(items=operations, next_cursor=next_cursor))


@dataclass(frozen=True, kw_only=True)
class GetAuditOperationQuery(Query):
    workspace_id: uuid.UUID
    operation_id: uuid.UUID


class GetAuditOperation:
    """Retrieve a single audit operation by ID."""

    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: GetAuditOperationQuery, auth: AuthContext | None = None
    ) -> Result[AuditOperation, DomainError]:
        require_workspace_role(auth, "viewer")
        operation = await self._repo.find_by_id_in_workspace(
            input.workspace_id, input.operation_id
        )
        if operation is None:
            return Failure(NotFoundError("AuditOperation", str(input.operation_id)))
        return Success(operation)
