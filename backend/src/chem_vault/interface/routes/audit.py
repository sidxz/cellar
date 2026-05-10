"""Audit trail query endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from chem_vault.application.audit.query_audit import (
    GetAuditOperationQuery,
    ListAuditOperationsQuery,
)
from chem_vault.domain.audit_compliance.models import AuditOperation
from chem_vault.interface.dependencies import (
    AuthDep,
    GetAuditOperationDep,
    ListAuditOperationsDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditEntryResponse(BaseModel):
    id: uuid.UUID
    field_name: str
    old_value: str | None
    new_value: str | None
    entry_type: str

class ElectronicSignatureResponse(BaseModel):
    signer_id: uuid.UUID
    reason: str
    signed_at: datetime


class AuditOperationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    operation_type: str
    performed_by: uuid.UUID
    performed_at: datetime
    reason: str | None
    entries: list[AuditEntryResponse]
    signature: ElectronicSignatureResponse | None

    @classmethod
    def from_domain(cls, op: AuditOperation) -> AuditOperationResponse:
        return cls(
            id=op.id,
            workspace_id=op.workspace_id,
            entity_type=op.entity_type,
            entity_id=op.entity_id,
            operation_type=op.operation_type.value,
            performed_by=op.user_id,
            performed_at=op.started_at,
            reason=op.reason,
            entries=[
                AuditEntryResponse(
                    id=e.id,
                    field_name=e.field_name,
                    old_value=e.old_value,
                    new_value=e.new_value,
                    entry_type=e.action.value,
                )
                for e in op.entries
            ],
            signature=(
                ElectronicSignatureResponse(
                    signer_id=op.signature.user_id,
                    reason=op.signature.meaning,
                    signed_at=op.signature.signed_at,
                )
                if op.signature is not None
                else None
            ),
        )


@router.get("", response_model=list[AuditOperationResponse])
async def list_audit_operations(
    auth: AuthDep,
    use_case: ListAuditOperationsDep,
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AuditOperationResponse]:
    query = ListAuditOperationsQuery(
        workspace_id=auth.workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        limit=limit,
    )
    operations = result_to_response(await use_case(query, auth=auth))
    return [AuditOperationResponse.from_domain(op) for op in operations]


@router.get("/{operation_id}", response_model=AuditOperationResponse)
async def get_audit_operation(
    operation_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetAuditOperationDep,
) -> AuditOperationResponse:
    query = GetAuditOperationQuery(workspace_id=auth.workspace_id, operation_id=operation_id)
    operation = result_to_response(await use_case(query, auth=auth))
    return AuditOperationResponse.from_domain(operation)
