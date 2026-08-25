"""PlateGroup API routes — hierarchy CRUD, tree read model, plate assignment."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.plate_groups import (
    AssignPlatesToGroupCommand,
    CreatePlateGroupCommand,
    DeletePlateGroupCommand,
    GetGroupTreeQuery,
    GroupTree,
    GroupTreeNode,
    MovePlateGroupCommand,
    RemovePlatesFromGroupCommand,
    UpdatePlateGroupCommand,
)
from cellar.application.shared.sentinel import UNSET
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.interface.dependencies import (
    AssignPlatesToGroupDep,
    AuthDep,
    CreatePlateGroupDep,
    DeletePlateGroupDep,
    GetGroupTreeDep,
    MovePlateGroupDep,
    RemovePlatesFromGroupDep,
    UpdatePlateGroupDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/plate-groups", tags=["plate-groups"])


class PlateGroupResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    owner_org_id: uuid.UUID
    name: str
    parent_group_id: uuid.UUID | None = None
    group_type: str | None = None
    description: str | None = None
    state: str | None = None
    storage_location_id: uuid.UUID | None = None
    initial_volume_ul: float | None = None
    initial_concentration_mm: float | None = None
    compound_count: int | None = None
    scientist: str | None = None
    created_at: datetime
    created_by: uuid.UUID
    version: int

    @classmethod
    def from_domain(cls, g: PlateGroup) -> PlateGroupResponse:
        return cls(
            id=g.id,
            workspace_id=g.workspace_id,
            owner_org_id=g.owner_org_id,
            name=g.name,
            parent_group_id=g.parent_group_id,
            group_type=g.group_type,
            description=g.description,
            state=g.state,
            storage_location_id=g.storage_location_id,
            initial_volume_ul=g.initial_volume_ul,
            initial_concentration_mm=g.initial_concentration_mm,
            compound_count=g.compound_count,
            scientist=g.scientist,
            created_at=g.created_at,
            created_by=g.created_by,
            version=g.version,
        )


class GroupTreeNodeResponse(BaseModel):
    id: uuid.UUID
    name: str
    group_type: str | None = None
    description: str | None = None
    state: str | None = None
    storage_location_id: uuid.UUID | None = None
    initial_volume_ul: float | None = None
    initial_concentration_mm: float | None = None
    compound_count: int | None = None
    scientist: str | None = None
    created_at: datetime
    parent_group_id: uuid.UUID | None = None
    owner_org_id: uuid.UUID
    plate_count: int
    plate_format: str | None = None
    created_by: uuid.UUID
    version: int
    children: list[GroupTreeNodeResponse] = []

    @classmethod
    def from_node(cls, n: GroupTreeNode) -> GroupTreeNodeResponse:
        return cls(
            id=n.group.id,
            name=n.group.name,
            group_type=n.group.group_type,
            description=n.group.description,
            state=n.group.state,
            storage_location_id=n.group.storage_location_id,
            initial_volume_ul=n.group.initial_volume_ul,
            initial_concentration_mm=n.group.initial_concentration_mm,
            compound_count=n.group.compound_count,
            scientist=n.group.scientist,
            created_at=n.group.created_at,
            parent_group_id=n.group.parent_group_id,
            owner_org_id=n.group.owner_org_id,
            plate_count=n.plate_count,
            plate_format=n.plate_format,
            created_by=n.group.created_by,
            version=n.group.version,
            children=[cls.from_node(c) for c in n.children],
        )


GroupTreeNodeResponse.model_rebuild()


class GroupTreeResponse(BaseModel):
    org_id: uuid.UUID
    roots: list[GroupTreeNodeResponse]

    @classmethod
    def from_tree(cls, t: GroupTree) -> GroupTreeResponse:
        return cls(org_id=t.org_id, roots=[GroupTreeNodeResponse.from_node(r) for r in t.roots])


class CreatePlateGroupBody(BaseModel):
    name: str
    owner_org_id: uuid.UUID | None = None
    parent_group_id: uuid.UUID | None = None
    group_type: str | None = None
    description: str | None = None
    state: str | None = None
    storage_location_id: uuid.UUID | None = None
    initial_volume_ul: float | None = None
    initial_concentration_mm: float | None = None
    compound_count: int | None = None
    scientist: str | None = None

    model_config = {"extra": "forbid"}


class UpdatePlateGroupBody(BaseModel):
    name: str | None = None
    group_type: str | None = None
    description: str | None = None
    state: str | None = None
    storage_location_id: uuid.UUID | None = None
    initial_volume_ul: float | None = None
    initial_concentration_mm: float | None = None
    compound_count: int | None = None
    scientist: str | None = None

    model_config = {"extra": "forbid"}


class MovePlateGroupBody(BaseModel):
    parent_group_id: uuid.UUID | None

    model_config = {"extra": "forbid"}


class PlateIdsBody(BaseModel):
    plate_ids: list[uuid.UUID]

    model_config = {"extra": "forbid"}


@router.post("", response_model=PlateGroupResponse, status_code=201)
async def create_plate_group(
    body: CreatePlateGroupBody, auth: AuthDep, uc: CreatePlateGroupDep
) -> PlateGroupResponse:
    """Create a plate group (root or nested)."""
    command = CreatePlateGroupCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        created_by=auth.user_id,
        owner_org_id=body.owner_org_id,
        parent_group_id=body.parent_group_id,
        group_type=body.group_type,
        description=body.description,
        state=body.state,
        storage_location_id=body.storage_location_id,
        initial_volume_ul=body.initial_volume_ul,
        initial_concentration_mm=body.initial_concentration_mm,
        compound_count=body.compound_count,
        scientist=body.scientist,
    )
    group = result_to_response(await uc(command, auth=auth))
    return PlateGroupResponse.from_domain(group)


@router.get("/tree", response_model=GroupTreeResponse)
async def get_group_tree(
    auth: AuthDep, uc: GetGroupTreeDep, org_id: uuid.UUID | None = None
) -> GroupTreeResponse:
    """Org-scoped group tree with plate counts (defaults to the caller's org)."""
    query = GetGroupTreeQuery(workspace_id=auth.workspace_id, org_id=org_id)
    tree = result_to_response(await uc(query, auth=auth))
    return GroupTreeResponse.from_tree(tree)


@router.patch("/{group_id}", response_model=PlateGroupResponse)
async def update_plate_group(
    group_id: uuid.UUID, body: UpdatePlateGroupBody, auth: AuthDep, uc: UpdatePlateGroupDep
) -> PlateGroupResponse:
    """Rename / retype / redescribe a group."""
    provided = body.model_fields_set
    command = UpdatePlateGroupCommand(
        workspace_id=auth.workspace_id,
        group_id=group_id,
        name=body.name if "name" in provided else None,
        group_type=body.group_type if "group_type" in provided else UNSET,
        description=body.description if "description" in provided else UNSET,
        state=body.state if "state" in provided else UNSET,
        storage_location_id=(
            body.storage_location_id if "storage_location_id" in provided else UNSET
        ),
        initial_volume_ul=body.initial_volume_ul if "initial_volume_ul" in provided else UNSET,
        initial_concentration_mm=(
            body.initial_concentration_mm if "initial_concentration_mm" in provided else UNSET
        ),
        compound_count=body.compound_count if "compound_count" in provided else UNSET,
        scientist=body.scientist if "scientist" in provided else UNSET,
    )
    group = result_to_response(await uc(command, auth=auth))
    return PlateGroupResponse.from_domain(group)


@router.post("/{group_id}/move", response_model=PlateGroupResponse)
async def move_plate_group(
    group_id: uuid.UUID, body: MovePlateGroupBody, auth: AuthDep, uc: MovePlateGroupDep
) -> PlateGroupResponse:
    """Reparent a group (null parent = make it a root)."""
    command = MovePlateGroupCommand(
        workspace_id=auth.workspace_id,
        group_id=group_id,
        new_parent_group_id=body.parent_group_id,
    )
    group = result_to_response(await uc(command, auth=auth))
    return PlateGroupResponse.from_domain(group)


@router.delete("/{group_id}", status_code=204)
async def delete_plate_group(
    group_id: uuid.UUID, auth: AuthDep, uc: DeletePlateGroupDep
) -> None:
    """Delete a childless group; its plates are ungrouped, not deleted."""
    command = DeletePlateGroupCommand(workspace_id=auth.workspace_id, group_id=group_id)
    result_to_response(await uc(command, auth=auth))


@router.post("/{group_id}/plates", status_code=204)
async def assign_plates_to_group(
    group_id: uuid.UUID, body: PlateIdsBody, auth: AuthDep, uc: AssignPlatesToGroupDep
) -> None:
    """Assign plates to a group (moves them if already grouped elsewhere)."""
    command = AssignPlatesToGroupCommand(
        workspace_id=auth.workspace_id, group_id=group_id, plate_ids=body.plate_ids
    )
    result_to_response(await uc(command, auth=auth))


@router.delete("/{group_id}/plates", status_code=204)
async def remove_plates_from_group(
    group_id: uuid.UUID, body: PlateIdsBody, auth: AuthDep, uc: RemovePlatesFromGroupDep
) -> None:
    """Remove plates from a group (clears their group assignment)."""
    command = RemovePlatesFromGroupCommand(
        workspace_id=auth.workspace_id, group_id=group_id, plate_ids=body.plate_ids
    )
    result_to_response(await uc(command, auth=auth))
