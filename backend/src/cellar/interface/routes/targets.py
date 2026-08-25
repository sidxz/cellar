"""Target API routes — read-only mirror of prot-cellar's catalog (see sync_targets)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel

from cellar.application.screening.get_target import (
    GetTargetQuery,
    ListTargetsQuery,
)
from cellar.application.screening.sync_targets import SyncReport, SyncTargetsCommand
from cellar.domain.screening_assay.target import Target
from cellar.interface.dependencies import (
    AuthDep,
    GetTargetDep,
    ListTargetsDep,
    SyncTargetsDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor

router = APIRouter(prefix="/api/v1")

# Only the caller's own Duar credentials travel to prot-cellar (shared realm).
_FORWARDED_HEADERS = ("authorization", "x-authz-token")


def _forwarded_auth(request: Request) -> dict[str, str]:
    return {h: v for h in _FORWARDED_HEADERS if (v := request.headers.get(h))}


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
    chembl_id: str | None = None

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
            chembl_id=t.chembl_id,
        )


class TargetSyncReportResponse(BaseModel):
    fetched: int
    created: int
    updated: int
    skipped: int

    @classmethod
    def from_report(cls, r: SyncReport) -> TargetSyncReportResponse:
        return cls(fetched=r.fetched, created=r.created, updated=r.updated, skipped=r.skipped)


# ---------------------------------------------------------------------------
# Target routes
# ---------------------------------------------------------------------------


@router.get("/targets", response_model=PaginatedResponse[TargetResponse], tags=["targets"])
async def list_targets(
    request: Request,
    auth: AuthDep,
    uc: ListTargetsDep,
    cursor: str | None = None,
    limit: int | None = None,
) -> PaginatedResponse[TargetResponse]:
    query = ListTargetsQuery(
        workspace_id=auth.workspace_id,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
        forwarded_headers=_forwarded_auth(request),
    )
    page = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[TargetResponse.from_domain(t) for t in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/targets/sync", response_model=TargetSyncReportResponse, tags=["targets"])
async def sync_targets(
    request: Request, auth: AuthDep, uc: SyncTargetsDep
) -> TargetSyncReportResponse:
    """Admin: pull the full target catalog from prot-cellar into the local mirror."""
    cmd = SyncTargetsCommand(
        workspace_id=auth.workspace_id, forwarded_headers=_forwarded_auth(request), force=True
    )
    return TargetSyncReportResponse.from_report(result_to_response(await uc(cmd, auth=auth)))


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
