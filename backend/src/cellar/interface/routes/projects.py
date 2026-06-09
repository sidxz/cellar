"""Project CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from starlette.responses import Response

from cellar.application.research_organization.archive_project import ArchiveProjectCommand
from cellar.application.research_organization.create_project import CreateProjectCommand
from cellar.application.research_organization.get_project import GetProjectQuery, ListProjectsQuery
from cellar.application.research_organization.get_project_scope_stats import (
    GetProjectScopeStatsQuery,
)
from cellar.application.research_organization.manage_molecule_projects import (
    AddMoleculeToProjectCommand,
    RemoveMoleculeFromProjectCommand,
)
from cellar.application.research_organization.manage_project_members import (
    AddProjectMemberCommand,
    ListProjectMembersQuery,
    RemoveProjectMemberCommand,
    UpdateProjectMemberRoleCommand,
)
from cellar.application.research_organization.update_project import UpdateProjectCommand
from cellar.application.shared.sentinel import UNSET
from cellar.domain.research_organization.project import Project, ProjectStatus
from cellar.interface.dependencies import (
    AddMoleculeToProjectDep,
    AddProjectMemberDep,
    ArchiveProjectDep,
    AuthDep,
    CreateProjectDep,
    GetProjectDep,
    GetProjectScopeStatsDep,
    ListProjectMembersDep,
    ListProjectsDep,
    RemoveMoleculeFromProjectDep,
    RemoveProjectMemberDep,
    UpdateProjectDep,
    UpdateProjectMemberRoleDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor

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


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    auth: AuthDep,
    use_case: ListProjectsDep,
    cursor: str | None = None,
    limit: int | None = None,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
) -> PaginatedResponse[ProjectResponse]:
    query = ListProjectsQuery(
        workspace_id=auth.workspace_id,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
        tags=tags,
        tag_logic=tag_logic,
    )
    page = result_to_response(await use_case(query, auth=auth))
    return PaginatedResponse(
        items=[ProjectResponse.from_domain(p) for p in page.items],
        next_cursor=page.next_cursor,
    )


class ProjectScopeStatsResponse(BaseModel):
    molecule_count: int
    protocol_count: int
    run_count: int
    campaign_count: int
    last_activity_at: datetime | None = None
    member_count: int
    member_ids: list[uuid.UUID]


@router.get(
    "/stats",
    response_model=dict[uuid.UUID, ProjectScopeStatsResponse],
)
async def get_project_scope_stats(
    auth: AuthDep,
    use_case: GetProjectScopeStatsDep,
    project_ids: list[uuid.UUID] = Query(default_factory=list),
) -> dict[uuid.UUID, ProjectScopeStatsResponse]:
    query = GetProjectScopeStatsQuery(
        workspace_id=auth.workspace_id,
        project_ids=tuple(project_ids),
    )
    stats = result_to_response(await use_case(query, auth=auth))
    return {
        pid: ProjectScopeStatsResponse(
            molecule_count=s.molecule_count,
            protocol_count=s.protocol_count,
            run_count=s.run_count,
            campaign_count=s.campaign_count,
            last_activity_at=s.last_activity_at,
            member_count=s.member_count,
            member_ids=list(s.member_ids),
        )
        for pid, s in stats.items()
    }


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetProjectDep,
) -> ProjectResponse:
    query = GetProjectQuery(workspace_id=auth.workspace_id, project_id=project_id)
    project = result_to_response(await use_case(query, auth=auth))
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
        name=body.name if "name" in provided else UNSET,
        description=body.description if "description" in provided else UNSET,
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


class ProjectMemberResponse(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str


class AddMemberBody(BaseModel):
    user_id: uuid.UUID
    role: str = "viewer"


class UpdateMemberRoleBody(BaseModel):
    role: str


@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
async def list_members(
    project_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListProjectMembersDep,
) -> list[ProjectMemberResponse]:
    result = await use_case(
        ListProjectMembersQuery(workspace_id=auth.workspace_id, project_id=project_id)
    )
    members = result_to_response(result)
    return [
        ProjectMemberResponse(project_id=m.project_id, user_id=m.user_id, role=m.role.value)
        for m in members
    ]


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=201)
async def add_member(
    project_id: uuid.UUID,
    body: AddMemberBody,
    auth: AuthDep,
    use_case: AddProjectMemberDep,
) -> ProjectMemberResponse:
    result = await use_case(
        AddProjectMemberCommand(
            workspace_id=auth.workspace_id,
            project_id=project_id,
            user_id=body.user_id,
            role=body.role,
        ),
        auth=auth,
    )
    member = result_to_response(result)
    return ProjectMemberResponse(
        project_id=member.project_id, user_id=member.user_id, role=member.role.value
    )


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberResponse)
async def update_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMemberRoleBody,
    auth: AuthDep,
    use_case: UpdateProjectMemberRoleDep,
) -> ProjectMemberResponse:
    result = await use_case(
        UpdateProjectMemberRoleCommand(
            workspace_id=auth.workspace_id,
            project_id=project_id,
            user_id=user_id,
            role=body.role,
        ),
        auth=auth,
    )
    member = result_to_response(result)
    return ProjectMemberResponse(
        project_id=member.project_id, user_id=member.user_id, role=member.role.value
    )


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    auth: AuthDep,
    use_case: RemoveProjectMemberDep,
) -> Response:
    result = await use_case(
        RemoveProjectMemberCommand(
            workspace_id=auth.workspace_id,
            project_id=project_id,
            user_id=user_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.post("/{project_id}/molecules/{molecule_id}", status_code=204)
async def add_molecule_to_project(
    project_id: uuid.UUID,
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: AddMoleculeToProjectDep,
) -> Response:
    result = await use_case(
        AddMoleculeToProjectCommand(
            workspace_id=auth.workspace_id,
            project_id=project_id,
            molecule_id=molecule_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.delete("/{project_id}/molecules/{molecule_id}", status_code=204)
async def remove_molecule_from_project(
    project_id: uuid.UUID,
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: RemoveMoleculeFromProjectDep,
) -> Response:
    result = await use_case(
        RemoveMoleculeFromProjectCommand(
            workspace_id=auth.workspace_id,
            project_id=project_id,
            molecule_id=molecule_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)
