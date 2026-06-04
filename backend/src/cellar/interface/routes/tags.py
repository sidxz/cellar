"""Tag management + per-entity assignment routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from cellar.application.workspace_config.tagging.assign_tag import AssignTagCommand
from cellar.application.workspace_config.tagging.delete_tag import DeleteTagCommand
from cellar.application.workspace_config.tagging.get_tags_for_entity import (
    GetTagsForEntityQuery,
)
from cellar.application.workspace_config.tagging.list_tag_entities import (
    ListTagEntitiesQuery,
)
from cellar.application.workspace_config.tagging.list_tags import ListTagsQuery
from cellar.application.workspace_config.tagging.merge_tags import MergeTagsCommand
from cellar.application.workspace_config.tagging.rename_tag import RenameTagCommand
from cellar.application.workspace_config.tagging.set_entity_tags import (
    SetEntityTagsCommand,
    TagInput,
)
from cellar.application.workspace_config.tagging.unassign_tag import UnassignTagCommand
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.workspace_config.tagging.tag import (
    AssignedTag,
    Tag,
    TaggableEntityType,
)
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._workspace_config import (
    AssignTagDep,
    DeleteTagDep,
    GetTagsForEntityDep,
    ListTagEntitiesDep,
    ListTagsDep,
    MergeTagsDep,
    RenameTagDep,
    SetEntityTagsDep,
    UnassignTagDep,
)
from cellar.interface.error_handlers import result_to_response


class TagResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    key: str
    value: str | None
    created_by: uuid.UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, tag: Tag) -> TagResponse:
        return cls(
            id=tag.id,
            workspace_id=tag.workspace_id,
            key=tag.key,
            value=tag.value,
            created_by=tag.created_by,
            created_at=tag.created_at,
        )


class TaggedEntityResponse(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    label: str
    assigned_at: datetime


class EntityTagResponse(BaseModel):
    """A tag on an entity, plus the assignment provenance (who/when tagged it)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    key: str
    value: str | None
    created_by: uuid.UUID
    created_at: datetime
    assigned_by: uuid.UUID
    assigned_at: datetime

    @classmethod
    def from_domain(cls, assigned: AssignedTag) -> EntityTagResponse:
        return cls(
            id=assigned.tag.id,
            workspace_id=assigned.tag.workspace_id,
            key=assigned.tag.key,
            value=assigned.tag.value,
            created_by=assigned.tag.created_by,
            created_at=assigned.tag.created_at,
            assigned_by=assigned.assigned_by,
            assigned_at=assigned.assigned_at,
        )


class AssignTagBody(BaseModel):
    key: str
    value: str | None = None


class RenameTagBody(BaseModel):
    key: str
    value: str | None = None


class MergeTagBody(BaseModel):
    target_tag_id: uuid.UUID


class TagItemBody(BaseModel):
    key: str
    value: str | None = None


class SetEntityTagsBody(BaseModel):
    tags: list[TagItemBody]


_ENTITY_COLLECTIONS: dict[str, TaggableEntityType] = {
    "molecules": TaggableEntityType.MOLECULE,
    "protocols": TaggableEntityType.PROTOCOL,
    "projects": TaggableEntityType.PROJECT,
    "collections": TaggableEntityType.COLLECTION,
    "runs": TaggableEntityType.RUN,
    "campaigns": TaggableEntityType.CAMPAIGN,
    "batches": TaggableEntityType.BATCH,
    "plates": TaggableEntityType.PLATE,
}


def _resolve_entity_type(entity_collection: str) -> TaggableEntityType:
    entity_type = _ENTITY_COLLECTIONS.get(entity_collection)
    if entity_type is None:
        raise NotFoundError("Entity", entity_collection)
    return entity_type


# --- Management ---
router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
async def list_tags(
    auth: AuthDep,
    use_case: ListTagsDep,
    q: str | None = None,
    mine: bool = False,
    limit: int = 50,
) -> list[TagResponse]:
    query = ListTagsQuery(
        workspace_id=auth.workspace_id,
        q=q,
        created_by=auth.user_id if mine else None,
        limit=limit,
    )
    tags = result_to_response(await use_case(query, auth=auth))
    return [TagResponse.from_domain(t) for t in tags]


@router.patch("/{tag_id}", response_model=TagResponse)
async def rename_tag(
    tag_id: uuid.UUID,
    body: RenameTagBody,
    auth: AuthDep,
    use_case: RenameTagDep,
) -> TagResponse:
    command = RenameTagCommand(
        workspace_id=auth.workspace_id, tag_id=tag_id, key=body.key, value=body.value
    )
    tag = result_to_response(await use_case(command, auth=auth))
    return TagResponse.from_domain(tag)


@router.post("/{tag_id}/merge", response_model=TagResponse)
async def merge_tag(
    tag_id: uuid.UUID,
    body: MergeTagBody,
    auth: AuthDep,
    use_case: MergeTagsDep,
) -> TagResponse:
    command = MergeTagsCommand(
        workspace_id=auth.workspace_id,
        source_tag_id=tag_id,
        target_tag_id=body.target_tag_id,
    )
    tag = result_to_response(await use_case(command, auth=auth))
    return TagResponse.from_domain(tag)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteTagDep,
) -> Response:
    command = DeleteTagCommand(workspace_id=auth.workspace_id, tag_id=tag_id)
    result_to_response(await use_case(command, auth=auth))
    return Response(status_code=204)


@router.get("/{tag_id}/entities", response_model=list[TaggedEntityResponse])
async def list_tag_entities(
    tag_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListTagEntitiesDep,
    types: list[str] | None = Query(default=None),  # noqa: B008 - FastAPI query idiom
    limit: int = 200,
) -> list[TaggedEntityResponse]:
    query = ListTagEntitiesQuery(
        workspace_id=auth.workspace_id, tag_id=tag_id, types=types, limit=limit
    )
    rows = result_to_response(await use_case(query, auth=auth))
    return [
        TaggedEntityResponse(
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            label=r.label,
            assigned_at=r.assigned_at,
        )
        for r in rows
    ]


# --- Per-entity assignment (generic over entity collection) ---
assignment_router = APIRouter(prefix="/api/v1", tags=["tags"])


@assignment_router.get(
    "/{entity_collection}/{entity_id}/tags", response_model=list[EntityTagResponse]
)
async def get_entity_tags(
    entity_collection: str,
    entity_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetTagsForEntityDep,
) -> list[EntityTagResponse]:
    query = GetTagsForEntityQuery(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
    )
    assigned = result_to_response(await use_case(query, auth=auth))
    return [EntityTagResponse.from_domain(a) for a in assigned]


@assignment_router.post(
    "/{entity_collection}/{entity_id}/tags",
    response_model=TagResponse,
    status_code=201,
)
async def assign_entity_tag(
    entity_collection: str,
    entity_id: uuid.UUID,
    body: AssignTagBody,
    auth: AuthDep,
    use_case: AssignTagDep,
) -> TagResponse:
    command = AssignTagCommand(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
        key=body.key,
        value=body.value,
        assigned_by=auth.user_id,
    )
    tag = result_to_response(await use_case(command, auth=auth))
    return TagResponse.from_domain(tag)


@assignment_router.put(
    "/{entity_collection}/{entity_id}/tags", response_model=list[TagResponse]
)
async def set_entity_tags(
    entity_collection: str,
    entity_id: uuid.UUID,
    body: SetEntityTagsBody,
    auth: AuthDep,
    use_case: SetEntityTagsDep,
) -> list[TagResponse]:
    command = SetEntityTagsCommand(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
        tags=tuple(TagInput(key=t.key, value=t.value) for t in body.tags),
        assigned_by=auth.user_id,
    )
    tags = result_to_response(await use_case(command, auth=auth))
    return [TagResponse.from_domain(t) for t in tags]


@assignment_router.delete(
    "/{entity_collection}/{entity_id}/tags/{tag_id}", status_code=204
)
async def unassign_entity_tag(
    entity_collection: str,
    entity_id: uuid.UUID,
    tag_id: uuid.UUID,
    auth: AuthDep,
    use_case: UnassignTagDep,
) -> Response:
    command = UnassignTagCommand(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
        tag_id=tag_id,
    )
    result_to_response(await use_case(command, auth=auth))
    return Response(status_code=204)
