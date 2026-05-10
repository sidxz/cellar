"""PlateTemplate CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.screening.plate_templates import (
    CreatePlateTemplateCommand,
    DeletePlateTemplateCommand,
    GetPlateTemplateQuery,
    ListPlateTemplatesQuery,
    UpdatePlateTemplateCommand,
)
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.screening_assay.enums import PlateFormat
from chem_vault.domain.screening_assay.plate_template import PlateTemplate
from chem_vault.interface.dependencies import (
    AuthDep,
    CreatePlateTemplateDep,
    DeletePlateTemplateDep,
    GetPlateTemplateDep,
    ListPlateTemplatesDep,
    UpdatePlateTemplateDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/plate-templates", tags=["plate-templates"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class PlateTemplateResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    format: PlateFormat
    template_map: dict
    description: str | None = None
    created_by: uuid.UUID

    @classmethod
    def from_domain(cls, entity: PlateTemplate) -> PlateTemplateResponse:
        return cls(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            format=entity.format,
            template_map=entity.template_map,
            description=entity.description,
            created_by=entity.created_by,
        )


class CreatePlateTemplateBody(BaseModel):
    name: str
    format: PlateFormat
    template_map: dict
    description: str | None = None


class UpdatePlateTemplateBody(BaseModel):
    name: str | None = None
    format: PlateFormat | None = None
    template_map: dict | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=PlateTemplateResponse, status_code=201)
async def create_plate_template(
    body: CreatePlateTemplateBody,
    auth: AuthDep,
    use_case: CreatePlateTemplateDep,
) -> PlateTemplateResponse:
    command = CreatePlateTemplateCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        format=body.format,
        template_map=body.template_map,
        description=body.description,
        created_by=auth.user_id,
    )
    template = result_to_response(await use_case(command, auth=auth))
    return PlateTemplateResponse.from_domain(template)


@router.get("", response_model=list[PlateTemplateResponse])
async def list_plate_templates(
    auth: AuthDep,
    use_case: ListPlateTemplatesDep,
) -> list[PlateTemplateResponse]:
    query = ListPlateTemplatesQuery(workspace_id=auth.workspace_id)
    templates = result_to_response(await use_case(query, auth=auth))
    return [PlateTemplateResponse.from_domain(t) for t in templates]


@router.get("/{template_id}", response_model=PlateTemplateResponse)
async def get_plate_template(
    template_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetPlateTemplateDep,
) -> PlateTemplateResponse:
    query = GetPlateTemplateQuery(
        workspace_id=auth.workspace_id, template_id=template_id
    )
    template = result_to_response(await use_case(query, auth=auth))
    return PlateTemplateResponse.from_domain(template)


@router.patch("/{template_id}", response_model=PlateTemplateResponse)
async def update_plate_template(
    template_id: uuid.UUID,
    body: UpdatePlateTemplateBody,
    auth: AuthDep,
    use_case: UpdatePlateTemplateDep,
) -> PlateTemplateResponse:
    provided = body.model_fields_set
    command = UpdatePlateTemplateCommand(
        workspace_id=auth.workspace_id,
        template_id=template_id,
        name=body.name if "name" in provided else None,
        format=body.format if "format" in provided else None,
        template_map=body.template_map if "template_map" in provided else None,
        description=body.description if "description" in provided else UNSET,
    )
    template = result_to_response(await use_case(command, auth=auth))
    return PlateTemplateResponse.from_domain(template)


@router.delete("/{template_id}", status_code=204)
async def delete_plate_template(
    template_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeletePlateTemplateDep,
) -> None:
    command = DeletePlateTemplateCommand(
        workspace_id=auth.workspace_id, template_id=template_id
    )
    result_to_response(await use_case(command, auth=auth))
