"""Audit query use cases — read-only access to audit trail.

These use cases operate directly on the AuditRepository (no UoW needed)
because the audit repository manages its own session (append-only,
no transactional mutations).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.domain.audit_compliance.models import AuditOperation
from chem_vault.domain.audit_compliance.repository import AuditRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListAuditOperationsQuery(Query):
    workspace_id: uuid.UUID
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    limit: int = 50


class ListAuditOperations:
    """List audit operations with optional filters."""

    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: ListAuditOperationsQuery
    ) -> Result[list[AuditOperation], DomainError]:
        operations = await self._repo.find_all(
            input.workspace_id,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            user_id=input.user_id,
            limit=input.limit,
        )
        return Success(operations)


@dataclass(frozen=True, kw_only=True)
class GetAuditOperationQuery(Query):
    workspace_id: uuid.UUID
    operation_id: uuid.UUID


class GetAuditOperation:
    """Retrieve a single audit operation by ID."""

    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: GetAuditOperationQuery
    ) -> Result[AuditOperation, DomainError]:
        operation = await self._repo.find_by_id(input.operation_id)
        if operation is None or operation.workspace_id != input.workspace_id:
            return Failure(
                NotFoundError("AuditOperation", str(input.operation_id))
            )
        return Success(operation)
