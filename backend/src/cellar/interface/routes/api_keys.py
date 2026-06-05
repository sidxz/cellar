"""External API key CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.shared.sentinel import UNSET
from cellar.application.workspace_config.create_external_api_key import (
    CreateExternalApiKeyCommand,
)
from cellar.application.workspace_config.delete_external_api_key import (
    DeleteExternalApiKeyCommand,
)
from cellar.application.workspace_config.list_external_api_keys import (
    ListExternalApiKeysQuery,
)
from cellar.application.workspace_config.update_external_api_key import (
    UpdateExternalApiKeyCommand,
)
from cellar.domain.workspace_config.external_api_key import ExternalApiKey
from cellar.interface.dependencies import (
    AuthDep,
    CreateExternalApiKeyDep,
    DeleteExternalApiKeyDep,
    ListExternalApiKeysDep,
    UpdateExternalApiKeyDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


class ExternalApiKeyResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    key_name: str
    label: str
    description: str | None = None
    key_prefix: str
    is_active: bool
    created_by: uuid.UUID
    last_used_at: datetime | None = None
    version: int

    @classmethod
    def from_domain(cls, entry: ExternalApiKey) -> ExternalApiKeyResponse:
        return cls(
            id=entry.id,
            workspace_id=entry.workspace_id,
            key_name=entry.key_name,
            label=entry.label,
            description=entry.description,
            key_prefix=entry.key_prefix,
            is_active=entry.is_active,
            created_by=entry.created_by,
            last_used_at=entry.last_used_at,
            version=entry.version,
        )


class CreateExternalApiKeyBody(BaseModel):
    key_name: str
    label: str
    description: str | None = None
    secret_value: str


class UpdateExternalApiKeyBody(BaseModel):
    label: str | None = None
    description: str | None = None
    secret_value: str | None = None
    is_active: bool | None = None


@router.get("", response_model=list[ExternalApiKeyResponse])
async def list_api_keys(
    auth: AuthDep,
    use_case: ListExternalApiKeysDep,
) -> list[ExternalApiKeyResponse]:
    query = ListExternalApiKeysQuery(workspace_id=auth.workspace_id)
    entries = result_to_response(await use_case(query, auth=auth))
    return [ExternalApiKeyResponse.from_domain(e) for e in entries]


@router.post("", response_model=ExternalApiKeyResponse, status_code=201)
async def create_api_key(
    body: CreateExternalApiKeyBody,
    auth: AuthDep,
    use_case: CreateExternalApiKeyDep,
) -> ExternalApiKeyResponse:
    command = CreateExternalApiKeyCommand(
        workspace_id=auth.workspace_id,
        key_name=body.key_name,
        label=body.label,
        description=body.description,
        secret_value=body.secret_value,
    )
    entry = result_to_response(await use_case(command, auth=auth))
    return ExternalApiKeyResponse.from_domain(entry)


@router.patch("/{key_id}", response_model=ExternalApiKeyResponse)
async def update_api_key(
    key_id: uuid.UUID,
    body: UpdateExternalApiKeyBody,
    auth: AuthDep,
    use_case: UpdateExternalApiKeyDep,
) -> ExternalApiKeyResponse:

    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "key_id": key_id,
    }
    for attr in ("label", "description", "secret_value", "is_active"):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET

    command = UpdateExternalApiKeyCommand(**cmd_fields)
    entry = result_to_response(await use_case(command, auth=auth))
    return ExternalApiKeyResponse.from_domain(entry)


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteExternalApiKeyDep,
) -> None:
    command = DeleteExternalApiKeyCommand(
        workspace_id=auth.workspace_id,
        key_id=key_id,
    )
    result_to_response(await use_case(command, auth=auth))
