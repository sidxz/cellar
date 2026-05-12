"""Collection CRUD + membership endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cellar.application.research_organization.collection_membership import (
    AddMoleculesToCollectionCommand,
    ListCollectionMoleculesQuery,
    RemoveMoleculesFromCollectionCommand,
)
from cellar.application.research_organization.compose_collections import ComposeCollectionsCommand
from cellar.application.research_organization.create_collection import CreateCollectionCommand
from cellar.application.research_organization.delete_collection import DeleteCollectionCommand
from cellar.application.research_organization.get_collection import (
    GetCollectionQuery,
    ListCollectionsQuery,
)
from cellar.application.research_organization.update_collection import UpdateCollectionCommand
from cellar.application.shared.molecule_resolver import MoleculeReference, RefType
from cellar.application.shared.sentinel import UNSET
from cellar.domain.research_organization.collection import Collection
from cellar.interface.dependencies import (
    AddMoleculesToCollectionDep,
    AuthDep,
    ComposeCollectionsDep,
    CreateCollectionDep,
    DeleteCollectionDep,
    GetCollectionDep,
    ListCollectionMoleculesDep,
    ListCollectionsDep,
    RemoveMoleculesFromCollectionDep,
    UpdateCollectionDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


class CollectionResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    project_id: uuid.UUID | None = None
    owned_by_org_id: uuid.UUID | None = None
    created_by: uuid.UUID
    molecule_count: int
    visibility: str
    version: int

    @classmethod
    def from_domain(cls, coll: Collection) -> CollectionResponse:
        return cls(
            id=coll.id,
            workspace_id=coll.workspace_id,
            name=coll.name,
            description=coll.description,
            project_id=coll.project_id,
            owned_by_org_id=coll.owned_by_org_id,
            created_by=coll.created_by,
            molecule_count=coll.molecule_count,
            visibility=coll.visibility.value,
            version=coll.version,
        )


class CreateCollectionBody(BaseModel):
    name: str
    description: str | None = None
    project_id: uuid.UUID | None = None
    owned_by_org_id: uuid.UUID | None = None
    visibility: str = "private"


class UpdateCollectionBody(BaseModel):
    name: str | None = None
    description: str | None = None
    project_id: uuid.UUID | None = None
    owned_by_org_id: uuid.UUID | None = None
    visibility: str | None = None

    model_config = {"extra": "forbid"}


class ComposeCollectionsBody(BaseModel):
    operation: str
    collection_ids: list[uuid.UUID]
    result_name: str


class MoleculeReferenceBody(BaseModel):
    value: str
    ref_type: str  # "uuid", "registration_number", "external_id", "smiles", "inchi_key", "name"


class AddMoleculesBody(BaseModel):
    references: list[MoleculeReferenceBody]


class RemoveMoleculesBody(BaseModel):
    molecule_ids: list[uuid.UUID]


class UnresolvedMoleculeResponse(BaseModel):
    value: str
    ref_type: str
    reason: str


class MembershipResultResponse(BaseModel):
    added_count: int
    already_present: int
    unresolved: list[UnresolvedMoleculeResponse]


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    auth: AuthDep,
    use_case: ListCollectionsDep,
    project_ids: list[uuid.UUID] | None = Query(default=None),
) -> list[CollectionResponse]:
    query = ListCollectionsQuery(
        workspace_id=auth.workspace_id,
        project_ids=tuple(project_ids) if project_ids else None,
    )
    collections = result_to_response(await use_case(query, auth=auth))
    return [CollectionResponse.from_domain(c) for c in collections]


@router.post("/compose", response_model=CollectionResponse, status_code=201)
async def compose_collections(
    body: ComposeCollectionsBody,
    auth: AuthDep,
    use_case: ComposeCollectionsDep,
) -> CollectionResponse:
    """Create a new collection from a boolean set operation on existing collections."""
    cmd = ComposeCollectionsCommand(
        workspace_id=auth.workspace_id,
        operation=body.operation,
        collection_ids=body.collection_ids,
        result_name=body.result_name,
        created_by=auth.user_id,
    )
    collection = result_to_response(await use_case(cmd, auth=auth))
    return CollectionResponse.from_domain(collection)


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetCollectionDep,
) -> CollectionResponse:
    query = GetCollectionQuery(workspace_id=auth.workspace_id, collection_id=collection_id)
    collection = result_to_response(await use_case(query, auth=auth))
    return CollectionResponse.from_domain(collection)


@router.post("", response_model=CollectionResponse, status_code=201)
async def create_collection(
    body: CreateCollectionBody,
    auth: AuthDep,
    use_case: CreateCollectionDep,
) -> CollectionResponse:
    command = CreateCollectionCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        project_id=body.project_id,
        owned_by_org_id=body.owned_by_org_id,
        created_by=auth.user_id,
        visibility=body.visibility,
    )
    collection = result_to_response(await use_case(command, auth=auth))
    return CollectionResponse.from_domain(collection)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    body: UpdateCollectionBody,
    auth: AuthDep,
    use_case: UpdateCollectionDep,
) -> CollectionResponse:
    provided = body.model_fields_set
    command = UpdateCollectionCommand(
        workspace_id=auth.workspace_id,
        collection_id=collection_id,
        name=body.name if "name" in provided else UNSET,
        description=body.description if "description" in provided else UNSET,
        project_id=body.project_id if "project_id" in provided else UNSET,
        owned_by_org_id=body.owned_by_org_id if "owned_by_org_id" in provided else UNSET,
        visibility=body.visibility if "visibility" in provided else UNSET,
    )
    collection = result_to_response(await use_case(command, auth=auth))
    return CollectionResponse.from_domain(collection)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteCollectionDep,
) -> None:
    command = DeleteCollectionCommand(workspace_id=auth.workspace_id, collection_id=collection_id)
    result_to_response(await use_case(command, auth=auth))


@router.post(
    "/{collection_id}/molecules",
    response_model=MembershipResultResponse,
    status_code=201,
)
async def add_molecules_to_collection(
    collection_id: uuid.UUID,
    body: AddMoleculesBody,
    auth: AuthDep,
    use_case: AddMoleculesToCollectionDep,
) -> MembershipResultResponse:
    refs = [
        MoleculeReference(value=r.value, ref_type=RefType(r.ref_type)) for r in body.references
    ]
    command = AddMoleculesToCollectionCommand(
        workspace_id=auth.workspace_id,
        collection_id=collection_id,
        refs=refs,
        added_by=auth.user_id,
    )
    result = result_to_response(await use_case(command, auth=auth))
    return MembershipResultResponse(
        added_count=len(result.added),
        already_present=result.already_present,
        unresolved=[
            UnresolvedMoleculeResponse(
                value=u.ref.value, ref_type=u.ref.ref_type.value, reason=u.reason
            )
            for u in result.unresolved
        ],
    )


@router.delete("/{collection_id}/molecules", status_code=200)
async def remove_molecules_from_collection(
    collection_id: uuid.UUID,
    body: RemoveMoleculesBody,
    auth: AuthDep,
    use_case: RemoveMoleculesFromCollectionDep,
) -> dict[str, int]:
    command = RemoveMoleculesFromCollectionCommand(
        workspace_id=auth.workspace_id,
        collection_id=collection_id,
        molecule_ids=body.molecule_ids,
    )
    removed_count = result_to_response(await use_case(command, auth=auth))
    return {"removed_count": removed_count}


@router.get("/{collection_id}/molecules", response_model=list[uuid.UUID])
async def list_collection_molecules(
    collection_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListCollectionMoleculesDep,
    offset: int = 0,
    limit: int = 100,
) -> list[uuid.UUID]:
    query = ListCollectionMoleculesQuery(
        workspace_id=auth.workspace_id,
        collection_id=collection_id,
        offset=offset,
        limit=limit,
    )
    molecule_ids = result_to_response(await use_case(query, auth=auth))
    return molecule_ids
