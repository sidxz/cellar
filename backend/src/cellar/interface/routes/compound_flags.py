"""Compound Flag API routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.screening.create_compound_flag import CreateCompoundFlagCommand
from cellar.application.screening.delete_compound_flag import DeleteCompoundFlagCommand
from cellar.application.screening.list_compound_flags import ListCompoundFlagsQuery
from cellar.domain.screening_assay.compound_flag import CompoundFlag
from cellar.interface.dependencies import (
    AuthDep,
    CreateCompoundFlagDep,
    DeleteCompoundFlagDep,
    ListCompoundFlagsDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["compound-flags"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class CompoundFlagResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    protocol_id: uuid.UUID
    flagged_by: uuid.UUID
    flag_type: str
    note: str | None = None
    created_at: datetime

    @classmethod
    def from_domain(cls, f: CompoundFlag) -> CompoundFlagResponse:
        return cls(
            id=f.id,
            workspace_id=f.workspace_id,
            molecule_id=f.molecule_id,
            protocol_id=f.protocol_id,
            flagged_by=f.flagged_by,
            flag_type=f.flag_type.value,
            note=f.note,
            created_at=f.created_at,
        )


class CreateFlagRequest(BaseModel):
    molecule_id: uuid.UUID
    flag_type: str = "star"
    note: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/protocols/{protocol_id}/flags",
    response_model=list[CompoundFlagResponse],
)
async def list_flags(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListCompoundFlagsDep,
) -> list[CompoundFlagResponse]:
    query = ListCompoundFlagsQuery(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
    )
    flags = result_to_response(await use_case(query))
    return [CompoundFlagResponse.from_domain(f) for f in flags]


@router.post(
    "/protocols/{protocol_id}/flags",
    response_model=CompoundFlagResponse,
    status_code=201,
)
async def create_flag(
    protocol_id: uuid.UUID,
    body: CreateFlagRequest,
    auth: AuthDep,
    use_case: CreateCompoundFlagDep,
) -> CompoundFlagResponse:
    command = CreateCompoundFlagCommand(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        protocol_id=protocol_id,
        flag_type=body.flag_type,
        note=body.note,
    )
    flag = result_to_response(await use_case(command, auth=auth))
    return CompoundFlagResponse.from_domain(flag)


@router.delete("/protocols/{protocol_id}/flags/{flag_id}", status_code=204)
async def delete_flag(
    protocol_id: uuid.UUID,
    flag_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteCompoundFlagDep,
) -> None:
    command = DeleteCompoundFlagCommand(
        workspace_id=auth.workspace_id,
        flag_id=flag_id,
    )
    result_to_response(await use_case(command, auth=auth))
