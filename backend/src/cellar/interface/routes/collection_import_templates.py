"""CRUD endpoints for CollectionImportTemplate."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cellar.application.research_organization.collection_import_templates import (
    CreateCollectionImportTemplateCommand,
    DeleteCollectionImportTemplateCommand,
    ListCollectionImportTemplatesQuery,
    UpdateCollectionImportTemplateCommand,
)
from cellar.interface.dependencies import (
    AuthDep,
    CreateCollectionImportTemplateDep,
    DeleteCollectionImportTemplateDep,
    ListCollectionImportTemplatesDep,
    UpdateCollectionImportTemplateDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(
    prefix="/api/v1/collection-import-templates",
    tags=["collection-import"],
)


class CollectionImportTemplateResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    column_mapping: dict[str, str]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None
    used_in_this_collection: bool = False


class CreateCollectionImportTemplateRequest(BaseModel):
    name: str
    description: str | None = None
    column_mapping: dict[str, str]


class UpdateCollectionImportTemplateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    column_mapping: dict[str, str] | None = None


def _to_response(  # type: ignore[no-untyped-def]
    template, collection_id: uuid.UUID | None = None
) -> CollectionImportTemplateResponse:
    used_here = collection_id is not None and collection_id in template.used_in_collections
    return CollectionImportTemplateResponse(
        id=template.id,
        workspace_id=template.workspace_id,
        name=template.name,
        description=template.description,
        column_mapping=template.column_mapping,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        used_in_this_collection=used_here,
    )


@router.get("", response_model=list[CollectionImportTemplateResponse])
async def list_collection_import_templates(
    auth: AuthDep,
    uc: ListCollectionImportTemplatesDep,
    collection_id: uuid.UUID | None = Query(default=None),
) -> list[CollectionImportTemplateResponse]:
    result = await uc(
        ListCollectionImportTemplatesQuery(workspace_id=auth.workspace_id),
        auth=auth,
    )
    templates = result_to_response(result)
    return [_to_response(t, collection_id=collection_id) for t in templates]


@router.post(
    "",
    response_model=CollectionImportTemplateResponse,
    status_code=201,
)
async def create_collection_import_template(
    auth: AuthDep,
    body: CreateCollectionImportTemplateRequest,
    uc: CreateCollectionImportTemplateDep,
) -> CollectionImportTemplateResponse:
    cmd = CreateCollectionImportTemplateCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        column_mapping=body.column_mapping,
        created_by=auth.user_id,
    )
    result = await uc(cmd, auth=auth)
    return _to_response(result_to_response(result))


@router.put(
    "/{template_id}",
    response_model=CollectionImportTemplateResponse,
)
async def update_collection_import_template(
    template_id: uuid.UUID,
    auth: AuthDep,
    body: UpdateCollectionImportTemplateRequest,
    uc: UpdateCollectionImportTemplateDep,
) -> CollectionImportTemplateResponse:
    cmd = UpdateCollectionImportTemplateCommand(
        workspace_id=auth.workspace_id,
        template_id=template_id,
        name=body.name,
        description=body.description,
        column_mapping=body.column_mapping,
    )
    result = await uc(cmd, auth=auth)
    return _to_response(result_to_response(result))


@router.delete("/{template_id}", status_code=204)
async def delete_collection_import_template(
    template_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteCollectionImportTemplateDep,
) -> None:
    cmd = DeleteCollectionImportTemplateCommand(
        workspace_id=auth.workspace_id,
        template_id=template_id,
    )
    result = await uc(cmd, auth=auth)
    result_to_response(result)
