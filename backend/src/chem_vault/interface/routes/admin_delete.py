"""Admin hard-delete endpoints — Tier 1 (RESTRICT) and Tier 2 (cascade).

Tier 1: any registered entity_type. RESTRICT-by-default — 409 if any
        inbound FK refs exist, with named blockers.
Tier 2: Protocol, Run, Molecule. Force-cascade with preview + typed-name confirm.
        (Tier 2 endpoints land in Task 14.)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from returns.result import Failure, Success

from chem_vault.application.admin.admin_hard_delete import (
    AdminHardDeleteCommand,
    BlockedByDependenciesError,
)
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from chem_vault.interface.dependencies import AdminHardDeleteDep, AuthDep

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AdminDeleteBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class BlockerPayload(BaseModel):
    table: str
    entity_type: str
    fk_column: str
    count: int
    samples: list[dict]
    truncated: bool


class BlockedByDependenciesResponse(BaseModel):
    error: str = "delete_blocked_by_dependencies"
    blockers: list[BlockerPayload]


@router.delete(
    "/{entity_type}/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        409: {"model": BlockedByDependenciesResponse},
        403: {"description": "Caller is not a workspace admin"},
        404: {"description": "Entity not found or unknown entity_type"},
    },
)
async def admin_hard_delete(
    entity_type: str,
    entity_id: uuid.UUID,
    body: AdminDeleteBody,
    auth: AuthDep,
    use_case: AdminHardDeleteDep,
) -> None:
    cmd = AdminHardDeleteCommand(
        workspace_id=auth.workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=body.reason,
    )
    result = await use_case(cmd, auth=auth)

    if isinstance(result, Success):
        return None

    err = result.failure()
    if isinstance(err, BlockedByDependenciesError):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "delete_blocked_by_dependencies",
                "blockers": [
                    {
                        "table": r.table,
                        "entity_type": r.entity_type,
                        "fk_column": r.fk_column,
                        "count": r.count,
                        "samples": r.samples,
                        "truncated": r.truncated,
                    }
                    for r in err.blockers
                ],
            },
        )
    if isinstance(err, AuthorizationError):
        raise HTTPException(status_code=403, detail=str(err))
    if isinstance(err, NotFoundError):
        raise HTTPException(status_code=404, detail=str(err))
    if isinstance(err, ValidationError):
        raise HTTPException(status_code=422, detail=str(err))
    raise HTTPException(status_code=500, detail=str(err))
