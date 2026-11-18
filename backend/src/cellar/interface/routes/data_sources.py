"""Data source CRUD + template preview endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.cdd_import.list_vault_fields import ListVaultFieldsQuery
from cellar.application.shared.sentinel import UNSET
from cellar.application.workspace_config.create_data_source import (
    CreateDataSourceCommand,
)
from cellar.application.workspace_config.delete_data_source import (
    DeleteDataSourceCommand,
)
from cellar.application.workspace_config.get_data_source import (
    GetDataSourceQuery,
)
from cellar.application.workspace_config.list_data_sources import (
    ListDataSourcesQuery,
)
from cellar.application.workspace_config.update_data_source import (
    UpdateDataSourceCommand,
)
from cellar.domain.workspace_config.data_source import (
    DataSource,
    EntityMapping,
    get_default_template,
)
from cellar.interface.dependencies import (
    AuthDep,
    CreateDataSourceDep,
    DeleteDataSourceDep,
    GetDataSourceDep,
    ListDataSourcesDep,
    ListVaultFieldsDep,
    UpdateDataSourceDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor
from cellar.interface.routes.bulk_registration import ColumnMappingColumnBody

router = APIRouter(prefix="/api/v1/data-sources", tags=["data-sources"])


# ======================================================================
# Pydantic response/request models
# ======================================================================


class IdStorageResponse(BaseModel):
    storage_type: str
    identifier_type: str | None = None
    custom_field_name: str | None = None


class FieldMappingResponse(BaseModel):
    source_field: str
    target_field: str
    target_type: str


class EntityMappingResponse(BaseModel):
    entity_type: str
    id_field: str
    id_storage: IdStorageResponse
    field_mappings: list[FieldMappingResponse]
    parent_path: str | None = None


class DataSourceResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    source_type: str
    config: dict[str, Any]
    api_key_name: str | None = None
    is_active: bool
    entity_mappings: list[EntityMappingResponse]
    # CDD sources: vault field path -> registration target (header = the vault field path).
    registration_mapping: list[ColumnMappingColumnBody] | None = None
    created_by: uuid.UUID
    version: int
    create_batch_on_duplicate: bool = False

    @classmethod
    def from_domain(cls, ds: DataSource) -> DataSourceResponse:
        return cls(
            id=ds.id,
            workspace_id=ds.workspace_id,
            name=ds.name,
            source_type=ds.source_type,
            config=ds.config,
            api_key_name=ds.api_key_name,
            is_active=ds.is_active,
            entity_mappings=[_em_to_response(em) for em in ds.entity_mappings],
            registration_mapping=(
                None
                if ds.registration_mapping is None
                else [ColumnMappingColumnBody(**c) for c in ds.registration_mapping]
            ),
            created_by=ds.created_by,
            version=ds.version,
            create_batch_on_duplicate=ds.create_batch_on_duplicate,
        )


class CreateDataSourceBody(BaseModel):
    name: str
    source_type: str
    config: dict[str, Any] = {}
    api_key_name: str | None = None


class UpdateDataSourceBody(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    config: dict[str, Any] | None = None
    api_key_name: str | None = None
    entity_mappings: list[dict[str, Any]] | None = None
    registration_mapping: list[ColumnMappingColumnBody] | None = None
    create_batch_on_duplicate: bool | None = None


class VaultField(BaseModel):
    path: str
    label: str


class VaultFieldsResponse(BaseModel):
    molecule: list[VaultField]
    batch: list[VaultField]


# ======================================================================
# Endpoints
# ======================================================================


@router.get("", response_model=PaginatedResponse[DataSourceResponse])
async def list_data_sources(
    auth: AuthDep,
    use_case: ListDataSourcesDep,
    cursor: str | None = None,
    limit: int | None = None,
) -> PaginatedResponse[DataSourceResponse]:
    query = ListDataSourcesQuery(
        workspace_id=auth.workspace_id,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
    )
    page = result_to_response(await use_case(query, auth=auth))
    return PaginatedResponse(
        items=[DataSourceResponse.from_domain(ds) for ds in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=DataSourceResponse, status_code=201)
async def create_data_source(
    body: CreateDataSourceBody,
    auth: AuthDep,
    use_case: CreateDataSourceDep,
) -> DataSourceResponse:
    command = CreateDataSourceCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        source_type=body.source_type,
        config=body.config,
        api_key_name=body.api_key_name,
    )
    ds = result_to_response(await use_case(command, auth=auth))
    return DataSourceResponse.from_domain(ds)


@router.get("/templates/{source_type}", response_model=list[EntityMappingResponse])
async def get_template(source_type: str, _auth: AuthDep) -> list[EntityMappingResponse]:
    """Preview default entity mappings for a source type (read-only reference)."""
    template = get_default_template(source_type)
    return [_em_to_response(em) for em in template]


@router.get("/{data_source_id}/vault-fields", response_model=VaultFieldsResponse)
async def get_vault_fields(
    data_source_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListVaultFieldsDep,
) -> VaultFieldsResponse:
    """The vault's own fields, for the registration mapper (admin)."""
    query = ListVaultFieldsQuery(workspace_id=auth.workspace_id, data_source_id=data_source_id)
    fields = result_to_response(await use_case(query, auth=auth))
    return VaultFieldsResponse(
        molecule=[VaultField(path=f.path, label=f.label) for f in fields.molecule],
        batch=[VaultField(path=f.path, label=f.label) for f in fields.batch],
    )


@router.get("/{data_source_id}", response_model=DataSourceResponse)
async def get_data_source(
    data_source_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetDataSourceDep,
) -> DataSourceResponse:
    query = GetDataSourceQuery(
        workspace_id=auth.workspace_id,
        data_source_id=data_source_id,
    )
    ds = result_to_response(await use_case(query, auth=auth))
    return DataSourceResponse.from_domain(ds)


@router.patch("/{data_source_id}", response_model=DataSourceResponse)
async def update_data_source(
    data_source_id: uuid.UUID,
    body: UpdateDataSourceBody,
    auth: AuthDep,
    use_case: UpdateDataSourceDep,
) -> DataSourceResponse:

    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "data_source_id": data_source_id,
    }
    for attr in ("name", "is_active", "config", "api_key_name", "entity_mappings"):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET

    if "registration_mapping" in body.model_fields_set:
        cmd_fields["registration_mapping"] = (
            None
            if body.registration_mapping is None
            else [c.model_dump(mode="json") for c in body.registration_mapping]
        )
    else:
        cmd_fields["registration_mapping"] = UNSET

    if "create_batch_on_duplicate" in body.model_fields_set:
        cmd_fields["create_batch_on_duplicate"] = body.create_batch_on_duplicate
    else:
        cmd_fields["create_batch_on_duplicate"] = UNSET

    command = UpdateDataSourceCommand(**cmd_fields)
    ds = result_to_response(await use_case(command, auth=auth))
    return DataSourceResponse.from_domain(ds)


@router.delete("/{data_source_id}", status_code=204)
async def delete_data_source(
    data_source_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteDataSourceDep,
) -> None:
    command = DeleteDataSourceCommand(
        workspace_id=auth.workspace_id,
        data_source_id=data_source_id,
    )
    result_to_response(await use_case(command, auth=auth))


# ======================================================================
# Helpers
# ======================================================================


def _em_to_response(em: EntityMapping) -> EntityMappingResponse:
    return EntityMappingResponse(
        entity_type=em.entity_type,
        id_field=em.id_field,
        id_storage=IdStorageResponse(
            storage_type=em.id_storage.storage_type,
            identifier_type=em.id_storage.identifier_type,
            custom_field_name=em.id_storage.custom_field_name,
        ),
        field_mappings=[
            FieldMappingResponse(
                source_field=fm.source_field,
                target_field=fm.target_field,
                target_type=fm.target_type,
            )
            for fm in em.field_mappings
        ],
        parent_path=em.parent_path,
    )
