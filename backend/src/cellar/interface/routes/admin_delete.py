"""Admin hard-delete endpoints — Tier 1 (RESTRICT) and Tier 2 (cascade).

Tier 1: any registered entity_type. RESTRICT-by-default — 409 if any
        inbound FK refs exist, with named blockers.
Tier 2: Protocol, Run, Molecule. Force-cascade with preview + typed-name confirm.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from cellar.application.admin.admin_hard_delete import AdminHardDeleteCommand
from cellar.application.admin.cascade_delete import CascadeDeleteCommand
from cellar.application.admin.cascade_preview import CascadePreviewQuery
from cellar.domain.shared.cascade import CascadeNode
from cellar.interface.dependencies import (
    AdminHardDeleteDep,
    AuthDep,
    CascadeDeleteDep,
    CascadePreviewDep,
)
from cellar.interface.error_handlers import result_to_response

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
    result_to_response(result)
    return None


# ---------------------------------------------------------------------------
# Tier-2 endpoints: cascade preview + cascade delete
# ---------------------------------------------------------------------------


class CascadeNodeResponse(BaseModel):
    entity_type: str
    table: str
    display_label: str
    count: int
    samples: list[dict]
    truncated: bool
    action: str
    children: list[CascadeNodeResponse] = []

    @classmethod
    def from_domain(cls, n: CascadeNode) -> CascadeNodeResponse:
        return cls(
            entity_type=n.entity_type,
            table=n.table,
            display_label=n.display_label,
            count=n.count,
            samples=n.samples,
            truncated=n.truncated,
            action=n.action.value,
            children=[cls.from_domain(c) for c in n.children],
        )


CascadeNodeResponse.model_rebuild()


@router.post(
    "/{entity_type}/{entity_id}/cascade-preview",
    response_model=CascadeNodeResponse,
)
async def cascade_preview(
    entity_type: str,
    entity_id: uuid.UUID,
    auth: AuthDep,
    use_case: CascadePreviewDep,
) -> CascadeNodeResponse:
    res = await use_case(
        CascadePreviewQuery(
            workspace_id=auth.workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
        ),
        auth=auth,
    )
    node = result_to_response(res)
    return CascadeNodeResponse.from_domain(node)


class CascadeDeleteBody(BaseModel):
    typed_name: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


@router.delete(
    "/{entity_type}/{entity_id}/cascade",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cascade_delete(
    entity_type: str,
    entity_id: uuid.UUID,
    body: CascadeDeleteBody,
    auth: AuthDep,
    use_case: CascadeDeleteDep,
) -> None:
    res = await use_case(
        CascadeDeleteCommand(
            workspace_id=auth.workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            typed_name=body.typed_name,
            reason=body.reason,
        ),
        auth=auth,
    )
    result_to_response(res)
    return None
