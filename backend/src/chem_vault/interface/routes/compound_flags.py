"""Compound Flag API routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.domain.screening_assay.compound_flag import CompoundFlag, FlagType
from chem_vault.interface.dependencies import AuthDep, UoWDep

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
    uow: UoWDep,
) -> list[CompoundFlagResponse]:
    from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_repository import (
        SQLAlchemyCompoundFlagRepository,
    )

    async with uow as u:
        repo = SQLAlchemyCompoundFlagRepository(u)
        flags = await repo.list_by_protocol(auth.workspace_id, protocol_id)
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
    uow: UoWDep,
) -> CompoundFlagResponse:
    from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_repository import (
        SQLAlchemyCompoundFlagRepository,
    )

    flag = CompoundFlag(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        protocol_id=protocol_id,
        flagged_by=auth.user_id,
        flag_type=FlagType(body.flag_type),
        note=body.note,
        created_at=datetime.now(timezone.utc),
    )
    async with uow as u:
        repo = SQLAlchemyCompoundFlagRepository(u)
        await repo.save(flag)
        await u.commit()
    return CompoundFlagResponse.from_domain(flag)


@router.delete("/protocols/{protocol_id}/flags/{flag_id}", status_code=204)
async def delete_flag(
    protocol_id: uuid.UUID,
    flag_id: uuid.UUID,
    auth: AuthDep,
    uow: UoWDep,
) -> None:
    from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_repository import (
        SQLAlchemyCompoundFlagRepository,
    )

    async with uow as u:
        repo = SQLAlchemyCompoundFlagRepository(u)
        await repo.delete(auth.workspace_id, flag_id)
        await u.commit()
