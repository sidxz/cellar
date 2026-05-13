"""Target API routes (biological targets for screening protocols)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.screening.create_target import CreateTarget, CreateTargetCommand
from cellar.application.screening.delete_target import DeleteTarget, DeleteTargetCommand
from cellar.application.screening.get_target import (
    GetTarget,
    GetTargetQuery,
    ListTargets,
    ListTargetsQuery,
)
from cellar.application.screening.update_target import UpdateTarget, UpdateTargetCommand
from cellar.application.shared.sentinel import UNSET
from cellar.domain.screening_assay.target import Target
from cellar.interface.dependencies import (
    AuthDep,
    CreateTargetDep,
    DeleteTargetDep,
    GetTargetDep,
    ListTargetsDep,
    UpdateTargetDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TargetResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    target_type: str
    organism: str | None = None
    gene_name: str | None = None
    uniprot_id: str | None = None
    ncbi_gene_id: str | None = None
    description: str | None = None
    target_class: str | None = None

    @classmethod
    def from_domain(cls, t: Target) -> TargetResponse:
        return cls(
            id=t.id,
            workspace_id=t.workspace_id,
            name=t.name,
            target_type=t.target_type.value,
            organism=t.organism,
            gene_name=t.gene_name,
            uniprot_id=t.uniprot_id,
            ncbi_gene_id=t.ncbi_gene_id,
            description=t.description,
            target_class=t.target_class,
        )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateTargetRequest(BaseModel):
    name: str
    target_type: str
    organism: str | None = None
    gene_name: str | None = None
    uniprot_id: str | None = None
    ncbi_gene_id: str | None = None
    description: str | None = None
    target_class: str | None = None
    sequence: str | None = None


class UpdateTargetRequest(BaseModel):
    name: str | None = None
    target_type: str | None = None
    organism: str | None = None
    gene_name: str | None = None
    uniprot_id: str | None = None
    ncbi_gene_id: str | None = None
    description: str | None = None
    target_class: str | None = None
    sequence: str | None = None


# ---------------------------------------------------------------------------
# Target routes
# ---------------------------------------------------------------------------


@router.post("/targets", response_model=TargetResponse, status_code=201, tags=["targets"])
async def create_target(
    auth: AuthDep,
    body: CreateTargetRequest,
    uc: CreateTargetDep,
) -> TargetResponse:
    cmd = CreateTargetCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        target_type=body.target_type,
        organism=body.organism,
        gene_name=body.gene_name,
        uniprot_id=body.uniprot_id,
        ncbi_gene_id=body.ncbi_gene_id,
        description=body.description,
        target_class=body.target_class,
        sequence=body.sequence,
    )
    result = await uc(cmd, auth=auth)
    return TargetResponse.from_domain(result_to_response(result))


@router.get("/targets", response_model=PaginatedResponse[TargetResponse], tags=["targets"])
async def list_targets(
    auth: AuthDep,
    uc: ListTargetsDep,
    cursor: str | None = None,
    limit: int | None = None,
) -> PaginatedResponse[TargetResponse]:
    query = ListTargetsQuery(
        workspace_id=auth.workspace_id,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
    )
    page = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[TargetResponse.from_domain(t) for t in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/targets/{target_id}", response_model=TargetResponse, tags=["targets"])
async def get_target(
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: GetTargetDep,
) -> TargetResponse:
    result = await uc(
        GetTargetQuery(workspace_id=auth.workspace_id, target_id=target_id),
        auth=auth,
    )
    return TargetResponse.from_domain(result_to_response(result))


@router.patch("/targets/{target_id}", response_model=TargetResponse, tags=["targets"])
async def update_target(
    target_id: uuid.UUID,
    body: UpdateTargetRequest,
    auth: AuthDep,
    uc: UpdateTargetDep,
) -> TargetResponse:

    cmd = UpdateTargetCommand(
        workspace_id=auth.workspace_id,
        target_id=target_id,
        name=body.name if "name" in body.model_fields_set else UNSET,
        target_type=body.target_type if "target_type" in body.model_fields_set else UNSET,
        organism=body.organism if "organism" in body.model_fields_set else UNSET,
        gene_name=body.gene_name if "gene_name" in body.model_fields_set else UNSET,
        uniprot_id=body.uniprot_id if "uniprot_id" in body.model_fields_set else UNSET,
        ncbi_gene_id=body.ncbi_gene_id if "ncbi_gene_id" in body.model_fields_set else UNSET,
        description=body.description if "description" in body.model_fields_set else UNSET,
        target_class=body.target_class if "target_class" in body.model_fields_set else UNSET,
        sequence=body.sequence if "sequence" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return TargetResponse.from_domain(result_to_response(result))


@router.delete("/targets/{target_id}", status_code=204, tags=["targets"])
async def delete_target(
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteTargetDep,
) -> None:
    cmd = DeleteTargetCommand(workspace_id=auth.workspace_id, target_id=target_id)
    result_to_response(await uc(cmd, auth=auth))
