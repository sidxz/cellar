"""Molecule relationship endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.chemical_registration.create_relationship import (
    CreateRelationshipCommand,
)
from cellar.application.chemical_registration.delete_relationship import (
    DeleteRelationshipCommand,
)
from cellar.application.chemical_registration.list_relationships import (
    ListRelationshipsQuery,
)
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.interface.dependencies import (
    AuthDep,
    CreateRelationshipDep,
    DeleteRelationshipDep,
    ListRelationshipsDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/molecules", tags=["molecules"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RelationshipResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    source_molecule_id: uuid.UUID
    target_molecule_id: uuid.UUID
    relationship_type: str
    notes: str | None = None
    created_by: uuid.UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, rel: MoleculeRelationship) -> RelationshipResponse:
        return cls(
            id=rel.id,
            workspace_id=rel.workspace_id,
            source_molecule_id=rel.source_molecule_id,
            target_molecule_id=rel.target_molecule_id,
            relationship_type=rel.relationship_type.value,
            notes=rel.notes,
            created_by=rel.created_by,
            created_at=rel.created_at,
        )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateRelationshipBody(BaseModel):
    target_molecule_id: uuid.UUID
    relationship_type: str
    notes: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{molecule_id}/relationships",
    response_model=RelationshipResponse,
    status_code=201,
)
async def create_relationship(
    molecule_id: uuid.UUID,
    body: CreateRelationshipBody,
    auth: AuthDep,
    use_case: CreateRelationshipDep,
) -> RelationshipResponse:
    command = CreateRelationshipCommand(
        workspace_id=auth.workspace_id,
        source_molecule_id=molecule_id,
        target_molecule_id=body.target_molecule_id,
        relationship_type=body.relationship_type,
        notes=body.notes,
        created_by=auth.user_id,
    )
    rel = result_to_response(await use_case(command, auth=auth))
    return RelationshipResponse.from_domain(rel)


@router.get(
    "/{molecule_id}/relationships",
    response_model=list[RelationshipResponse],
)
async def list_relationships(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListRelationshipsDep,
) -> list[RelationshipResponse]:
    query = ListRelationshipsQuery(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
    )
    rels = result_to_response(await use_case(query, auth=auth))
    return [RelationshipResponse.from_domain(r) for r in rels]


@router.delete(
    "/{molecule_id}/relationships/{relationship_id}",
    status_code=204,
)
async def delete_relationship(
    molecule_id: uuid.UUID,
    relationship_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteRelationshipDep,
) -> None:
    command = DeleteRelationshipCommand(
        workspace_id=auth.workspace_id,
        relationship_id=relationship_id,
    )
    result_to_response(await use_case(command, auth=auth))
