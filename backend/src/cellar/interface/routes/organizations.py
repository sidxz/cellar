"""Organization CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.shared.sentinel import UNSET
from cellar.application.workspace_config.create_organization import CreateOrganizationCommand
from cellar.application.workspace_config.get_organization import GetOrganizationQuery
from cellar.application.workspace_config.list_organizations import ListOrganizationsQuery
from cellar.application.workspace_config.update_organization import UpdateOrganizationCommand
from cellar.domain.workspace_config.enums import OrganizationType
from cellar.domain.workspace_config.organization import Organization
from cellar.interface.dependencies import (
    AuthDep,
    CreateOrganizationDep,
    GetOrganizationDep,
    ListOrganizationsDep,
    UpdateOrganizationDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    org_type: OrganizationType
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    is_active: bool
    version: int

    @classmethod
    def from_domain(cls, org: Organization) -> OrganizationResponse:
        return cls(
            id=org.id,
            workspace_id=org.workspace_id,
            name=org.name,
            org_type=org.org_type,
            contact_name=org.contact_name,
            contact_email=org.contact_email,
            notes=org.notes,
            is_active=org.is_active,
            version=org.version,
        )


class CreateOrganizationBody(BaseModel):
    name: str
    org_type: OrganizationType
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class UpdateOrganizationBody(BaseModel):
    name: str | None = None
    org_type: OrganizationType | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None

    model_config = {"extra": "forbid"}


@router.get("", response_model=PaginatedResponse[OrganizationResponse])
async def list_organizations(
    auth: AuthDep,
    use_case: ListOrganizationsDep,
    include_inactive: bool = False,
    cursor: str | None = None,
    limit: int | None = None,
) -> PaginatedResponse[OrganizationResponse]:
    query = ListOrganizationsQuery(
        workspace_id=auth.workspace_id,
        include_inactive=include_inactive,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
    )
    page = result_to_response(await use_case(query, auth=auth))
    return PaginatedResponse(
        items=[OrganizationResponse.from_domain(o) for o in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetOrganizationDep,
) -> OrganizationResponse:
    query = GetOrganizationQuery(workspace_id=auth.workspace_id, org_id=org_id)
    org = result_to_response(await use_case(query, auth=auth))
    return OrganizationResponse.from_domain(org)


@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    body: CreateOrganizationBody,
    auth: AuthDep,
    use_case: CreateOrganizationDep,
) -> OrganizationResponse:
    command = CreateOrganizationCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        org_type=body.org_type,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        notes=body.notes,
    )
    org = result_to_response(await use_case(command, auth=auth))
    return OrganizationResponse.from_domain(org)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: uuid.UUID,
    body: UpdateOrganizationBody,
    auth: AuthDep,
    use_case: UpdateOrganizationDep,
) -> OrganizationResponse:
    # Use model_fields_set to distinguish "omitted" from "explicitly null"
    provided = body.model_fields_set
    command = UpdateOrganizationCommand(
        workspace_id=auth.workspace_id,
        org_id=org_id,
        name=body.name if "name" in provided else None,
        org_type=body.org_type if "org_type" in provided else None,
        contact_name=body.contact_name if "contact_name" in provided else UNSET,
        contact_email=body.contact_email if "contact_email" in provided else UNSET,
        notes=body.notes if "notes" in provided else UNSET,
    )
    org = result_to_response(await use_case(command, auth=auth))
    return OrganizationResponse.from_domain(org)
