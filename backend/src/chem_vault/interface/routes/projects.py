"""Project CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.research_organization.archive_project import ArchiveProjectCommand
from chem_vault.application.research_organization.create_project import CreateProjectCommand
from chem_vault.application.research_organization.get_project import GetProjectQuery, ListProjectsQuery
from chem_vault.application.research_organization.update_project import UpdateProjectCommand
from chem_vault.domain.research_organization.project import Project, ProjectStatus
from chem_vault.interface.dependencies import (
    ArchiveProjectDep,
    AuthDep,
    CreateProjectDep,
    GetProjectDep,
    ListProjectsDep,
    UpdateProjectDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    status: ProjectStatus
    created_by: uuid.UUID
    version: int

    @classmethod
    def from_domain(cls, project: Project) -> ProjectResponse:
        return cls(
            id=project.id,
            workspace_id=project.workspace_id,
            name=project.name,
            description=project.description,
            status=project.status,
            created_by=project.created_by,
            version=project.version,
        )


class CreateProjectBody(BaseModel):
    name: str
    description: str | None = None


class UpdateProjectBody(BaseModel):
    name: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    auth: AuthDep,
    use_case: ListProjectsDep,
) -> list[ProjectResponse]:
    query = ListProjectsQuery(workspace_id=auth.workspace_id)
    projects = result_to_response(await use_case(query))
    return [ProjectResponse.from_domain(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetProjectDep,
) -> ProjectResponse:
    query = GetProjectQuery(workspace_id=auth.workspace_id, project_id=project_id)
    project = result_to_response(await use_case(query))
    return ProjectResponse.from_domain(project)


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: CreateProjectBody,
    auth: AuthDep,
    use_case: CreateProjectDep,
) -> ProjectResponse:
    command = CreateProjectCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        created_by=auth.user_id,
    )
    project = result_to_response(await use_case(command, auth=auth))
    return ProjectResponse.from_domain(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: UpdateProjectBody,
    auth: AuthDep,
    use_case: UpdateProjectDep,
) -> ProjectResponse:
    provided = body.model_fields_set
    command = UpdateProjectCommand(
        workspace_id=auth.workspace_id,
        project_id=project_id,
        name=body.name if "name" in provided else None,
        description=body.description if "description" in provided else ...,
    )
    project = result_to_response(await use_case(command, auth=auth))
    return ProjectResponse.from_domain(project)


@router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: uuid.UUID,
    auth: AuthDep,
    use_case: ArchiveProjectDep,
) -> ProjectResponse:
    command = ArchiveProjectCommand(
        workspace_id=auth.workspace_id,
        project_id=project_id,
        archived_by=auth.user_id,
    )
    project = result_to_response(await use_case(command, auth=auth))
    return ProjectResponse.from_domain(project)
