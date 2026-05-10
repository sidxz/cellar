"""Salt catalog CRUD endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from chem_vault.application.workspace_config.create_salt_entry import (
    CreateSaltEntry,
    CreateSaltEntryCommand,
)
from chem_vault.application.workspace_config.delete_salt_entry import (
    DeleteSaltEntry,
    DeleteSaltEntryCommand,
)
from chem_vault.application.workspace_config.list_salt_entries import (
    ListSaltEntries,
    ListSaltEntriesQuery,
)
from chem_vault.application.workspace_config.update_salt_entry import (
    UpdateSaltEntry,
    UpdateSaltEntryCommand,
    UNSET,
)
from chem_vault.domain.workspace_config.salt_entry import SaltEntry
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateSaltEntryDep,
    DeleteSaltEntryDep,
    ListSaltEntriesDep,
    UpdateSaltEntryDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/salt-catalog", tags=["salt-catalog"])


class SaltEntryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    code: str
    name: str
    smiles: str
    molecular_weight: float
    is_default: bool
    is_active: bool
    version: int

    @classmethod
    def from_domain(cls, entry: SaltEntry) -> SaltEntryResponse:
        return cls(
            id=entry.id,
            workspace_id=entry.workspace_id,
            code=entry.code,
            name=entry.name,
            smiles=entry.smiles,
            molecular_weight=entry.molecular_weight,
            is_default=entry.is_default,
            is_active=entry.is_active,
            version=entry.version,
        )


class CreateSaltEntryBody(BaseModel):
    code: str
    name: str
    smiles: str
    molecular_weight: float
    is_default: bool = False


class UpdateSaltEntryBody(BaseModel):
    name: str | None = None
    smiles: str | None = None
    molecular_weight: float | None = None
    is_active: bool | None = None


@router.get("", response_model=list[SaltEntryResponse])
async def list_salt_entries(
    auth: AuthDep,
    use_case: ListSaltEntriesDep,
    active_only: bool = True,
) -> list[SaltEntryResponse]:
    query = ListSaltEntriesQuery(
        workspace_id=auth.workspace_id,
        active_only=active_only,
    )
    entries = result_to_response(await use_case(query, auth=auth))
    return [SaltEntryResponse.from_domain(e) for e in entries]


@router.post("", response_model=SaltEntryResponse, status_code=201)
async def create_salt_entry(
    body: CreateSaltEntryBody,
    auth: AuthDep,
    use_case: CreateSaltEntryDep,
) -> SaltEntryResponse:
    command = CreateSaltEntryCommand(
        workspace_id=auth.workspace_id,
        code=body.code,
        name=body.name,
        smiles=body.smiles,
        molecular_weight=body.molecular_weight,
        is_default=body.is_default,
    )
    entry = result_to_response(await use_case(command, auth=auth))
    return SaltEntryResponse.from_domain(entry)


@router.patch("/{entry_id}", response_model=SaltEntryResponse)
async def update_salt_entry(
    entry_id: uuid.UUID,
    body: UpdateSaltEntryBody,
    auth: AuthDep,
    use_case: UpdateSaltEntryDep,
) -> SaltEntryResponse:
    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "entry_id": entry_id,
    }
    for attr in ("name", "smiles", "molecular_weight", "is_active"):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET

    command = UpdateSaltEntryCommand(**cmd_fields)
    entry = result_to_response(await use_case(command, auth=auth))
    return SaltEntryResponse.from_domain(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_salt_entry(
    entry_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteSaltEntryDep,
) -> None:
    command = DeleteSaltEntryCommand(
        workspace_id=auth.workspace_id,
        entry_id=entry_id,
    )
    result_to_response(await use_case(command, auth=auth))
