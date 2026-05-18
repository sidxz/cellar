"""POST /api/v1/sar/umap-cluster + GET/cancel job endpoints.

Three paths:
- POST 200 — cache hit or sync compute (≤500 molecules): returns result inline, job=null.
- POST 202 — async path (cache miss, >500 molecules): returns job=..., result=null.
- GET  /umap-cluster/jobs/{job_id} — poll status; includes result when status=ready.
- POST /umap-cluster/jobs/{job_id}/cancel — cancel a pending/running job (204).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator

from cellar.application.research_organization.collection_membership import (
    ListCollectionMoleculesQuery,
)
from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob
from cellar.application.sar_analysis.start_umap_cluster_job import (
    StartUmapClusterJob,
    StartUmapClusterJobInput,
)
from cellar.domain.sar_analysis.umap_job import UmapJob
from cellar.domain.sar_analysis.umap_types import UmapResult
from cellar.interface.error_handlers import result_to_response
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._research_organization import ListCollectionMoleculesDep
from cellar.interface.dependencies._sar_analysis import (
    CancelUmapClusterJobDep,
    GetUmapClusterJobDep,
    StartUmapClusterJobDep,
)

router = APIRouter(prefix="/api/v1/sar", tags=["sar-analysis"])

# Mol-count guardrails
MIN_SET_SIZE = 10
MAX_SET_SIZE = 50_000

# Expansion limit for collection-scoped queries (bypasses search pagination cap)
COLLECTION_EXPANSION_LIMIT = 100_000


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class StartUmapClusterBody(BaseModel):
    """Exactly one of ``collection_id`` or ``molecule_ids`` must be supplied.

    ``picker`` controls the representative-selection algorithm:
    - ``maxmin``: MaxMin diversity picker; ``n`` (required) sets the output count.
    - ``butina``: Butina cluster medoids; ``threshold`` drives the picks AND the coloring.

    ``threshold`` is the Butina cluster threshold (Tanimoto distance) that always
    drives the per-compound cluster coloring on the scatter, regardless of picker.
    Defaults to 0.4 when omitted. When ``picker=butina``, this same threshold
    also drives the medoid picks (single source of truth).
    """

    collection_id: UUID | None = None
    molecule_ids: list[UUID] | None = None
    picker: str = Field(..., pattern="^(maxmin|butina)$")
    n: int | None = Field(None, ge=1, le=10_000)
    threshold: float | None = Field(None, ge=0.05, le=0.95)

    @model_validator(mode="after")
    def _check_exactly_one_source(self) -> "StartUmapClusterBody":
        has_collection = self.collection_id is not None
        has_mols = bool(self.molecule_ids)
        if has_collection == has_mols:
            raise ValueError("Provide exactly one of collection_id or molecule_ids.")
        return self

    @model_validator(mode="after")
    def _check_picker_params(self) -> "StartUmapClusterBody":
        if self.picker == "maxmin" and self.n is None:
            raise ValueError("n is required when picker=maxmin.")
        return self


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class UmapPointDto(BaseModel):
    molecule_id: UUID
    x: float
    y: float


class ClusterAssignmentDto(BaseModel):
    molecule_id: UUID
    cluster_id: int


class RepresentativeDto(BaseModel):
    molecule_id: UUID
    cluster_id: int


class UmapResultDto(BaseModel):
    points: list[UmapPointDto]
    clusters: list[ClusterAssignmentDto]
    representatives: list[RepresentativeDto]
    cluster_count: int
    picker: str
    picker_params: dict
    skipped_molecule_ids: list[UUID]


class UmapJobDto(BaseModel):
    id: UUID
    status: str
    picker: str
    picker_params: dict
    error_message: str | None = None


class StartUmapClusterResponse(BaseModel):
    result: UmapResultDto | None
    job: UmapJobDto | None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _result_to_dto(r: UmapResult) -> UmapResultDto:
    return UmapResultDto(
        points=[UmapPointDto(molecule_id=p.molecule_id, x=p.x, y=p.y) for p in r.points],
        clusters=[
            ClusterAssignmentDto(molecule_id=c.molecule_id, cluster_id=c.cluster_id)
            for c in r.clusters
        ],
        representatives=[
            RepresentativeDto(molecule_id=rp.molecule_id, cluster_id=rp.cluster_id)
            for rp in r.representatives
        ],
        cluster_count=r.cluster_count,
        picker=r.picker,
        picker_params=r.picker_params,
        skipped_molecule_ids=r.skipped_molecule_ids,
    )


def _job_to_dto(j: UmapJob) -> UmapJobDto:
    return UmapJobDto(
        id=j.id,
        status=j.status.value,
        picker=j.picker,
        picker_params=j.picker_params,
        error_message=j.error_message,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/umap-cluster", status_code=status.HTTP_200_OK)
async def start_umap_cluster(
    body: StartUmapClusterBody,
    response: Response,
    auth: AuthDep,
    uc: StartUmapClusterJobDep,
    list_collection_members: ListCollectionMoleculesDep,
) -> StartUmapClusterResponse:
    """Compute or schedule a UMAP cluster map.

    Accepts either ``molecule_ids`` (explicit list) or ``collection_id``
    (server-side expansion to full member set).

    Returns 200 with ``result`` populated on cache hit or small (≤500) sets.
    Returns 202 with ``job`` populated when async computation is scheduled.
    """
    if body.collection_id is not None:
        # Expand collection server-side — ListCollectionMolecules handles
        # workspace-scoping; result_to_response raises HTTPException on Failure.
        molecule_ids = result_to_response(
            await list_collection_members(
                ListCollectionMoleculesQuery(
                    workspace_id=auth.workspace_id,
                    collection_id=body.collection_id,
                    offset=0,
                    limit=COLLECTION_EXPANSION_LIMIT,
                ),
                auth=auth,
            )
        )
    else:
        # Dedupe preserving order
        molecule_ids = list(dict.fromkeys(body.molecule_ids or []))

    if len(molecule_ids) < MIN_SET_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Need at least {MIN_SET_SIZE} molecules for UMAP.",
        )
    if len(molecule_ids) > MAX_SET_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cluster map capped at {MAX_SET_SIZE} molecules; refine the filter.",
        )

    # `threshold` is always part of picker_params — it drives the Butina coloring
    # for both picker modes. When picker=butina it ALSO drives the medoid picks.
    # When omitted by the caller, server default is 0.4 (chemistry convention
    # for ECFP4-like fingerprints).
    cluster_threshold = body.threshold if body.threshold is not None else 0.4
    picker_params: dict = (
        {"n": body.n, "threshold": cluster_threshold}
        if body.picker == "maxmin"
        else {"threshold": cluster_threshold}
    )

    out = await uc.execute(
        StartUmapClusterJobInput(
            molecule_ids=molecule_ids,
            picker=body.picker,
            picker_params=picker_params,
            workspace_id=auth.workspace_id,
            requested_by=auth.user_id,
            now=datetime.now(timezone.utc),
        )
    )

    if out.result is not None:
        return StartUmapClusterResponse(result=_result_to_dto(out.result), job=None)

    response.status_code = status.HTTP_202_ACCEPTED
    return StartUmapClusterResponse(result=None, job=_job_to_dto(out.job))  # type: ignore[arg-type]


@router.get("/umap-cluster/jobs/{job_id}")
async def get_umap_cluster_job(
    job_id: UUID,
    auth: AuthDep,
    uc: GetUmapClusterJobDep,
) -> StartUmapClusterResponse:
    """Poll the status of an async UMAP cluster job.

    Returns the computed result once ``status == "ready"``.
    """
    job = await uc.execute(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UMAP job not found.")
    return StartUmapClusterResponse(
        result=_result_to_dto(job.result) if job.result is not None else None,
        job=_job_to_dto(job),
    )


@router.post("/umap-cluster/jobs/{job_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_umap_cluster_job(
    job_id: UUID,
    auth: AuthDep,
    uc: CancelUmapClusterJobDep,
) -> None:
    """Request cancellation of a pending or running UMAP cluster job."""
    await uc.execute(job_id)
