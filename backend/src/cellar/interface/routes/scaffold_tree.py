"""POST /api/v1/scaffold-tree + GET/cancel job endpoints.

Three paths:
- POST 200 — cache hit or sync compute (≤500 molecules): returns tree inline, job=null.
- POST 202 — async path (cache miss, >500 molecules): returns job=..., tree=null.
- GET  /jobs/{job_id} — poll status; includes tree when status=ready.
- POST /jobs/{job_id}/cancel — cancel a pending/running job.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from cellar.application.sar_analysis.cancel_scaffold_tree_job import (
    CancelScaffoldTreeJob,
    CancelScaffoldTreeJobInput,
)
from cellar.application.sar_analysis.get_scaffold_tree_job import (
    GetScaffoldTreeJob,
    GetScaffoldTreeJobInput,
    ScaffoldTreeJobNotFound,
)
from cellar.application.sar_analysis.start_scaffold_tree_job import (
    StartScaffoldTreeJob,
    StartScaffoldTreeJobInput,
)
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._sar_analysis import (
    CancelScaffoldTreeJobDep,
    GetScaffoldTreeJobDep,
    StartScaffoldTreeJobDep,
)

router = APIRouter(prefix="/api/v1/scaffold-tree", tags=["scaffold-tree"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class StartScaffoldTreeRequest(BaseModel):
    molecule_ids: list[UUID]


class JobView(BaseModel):
    id: UUID
    status: str
    ids_hash: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class StartScaffoldTreeResponse(BaseModel):
    tree: dict | None
    job: JobView | None


class JobDetailResponse(BaseModel):
    id: UUID
    status: str
    ids_hash: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    tree: dict | None = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_tree(tree: ScaffoldTreeResult) -> dict:
    return {
        "nodes": [
            {
                "scaffold_smiles": n.scaffold_smiles,
                "molecule_ids": [str(m) for m in n.molecule_ids],
                "molecule_count": n.molecule_count,
                "subtree_molecule_count": n.subtree_molecule_count,
            }
            for n in tree.nodes
        ],
        "edges": [
            {"parent_smiles": e.parent_smiles, "child_smiles": e.child_smiles}
            for e in tree.edges
        ],
        "stats": dataclasses.asdict(tree.stats),
    }


def _serialize_job(job: ScaffoldTreeJob) -> JobView:
    return JobView(
        id=job.id,
        status=job.status.value,
        ids_hash=job.ids_hash,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_200_OK)
async def start_scaffold_tree(
    payload: StartScaffoldTreeRequest,
    response: Response,
    auth: AuthDep,
    uc: StartScaffoldTreeJobDep,
) -> StartScaffoldTreeResponse:
    """Compute or schedule a scaffold tree for the given molecule IDs.

    Returns 200 with ``tree`` populated on cache hit or small (≤500) sets.
    Returns 202 with ``job`` populated when async computation is scheduled.
    """
    out = await uc.execute(
        StartScaffoldTreeJobInput(
            molecule_ids=list(payload.molecule_ids),
            workspace_id=auth.workspace_id,
            requested_by=auth.user_id,
            now=datetime.now(timezone.utc),
        )
    )
    if out.tree is not None:
        return StartScaffoldTreeResponse(tree=_serialize_tree(out.tree), job=None)
    response.status_code = status.HTTP_202_ACCEPTED
    return StartScaffoldTreeResponse(tree=None, job=_serialize_job(out.job))  # type: ignore[arg-type]


@router.get("/jobs/{job_id}")
async def get_scaffold_tree_job(
    job_id: UUID,
    auth: AuthDep,
    uc: GetScaffoldTreeJobDep,
) -> JobDetailResponse:
    """Poll the status of an async scaffold tree job.

    Returns the computed tree once ``status == "ready"``.
    """
    try:
        job = await uc.execute(
            GetScaffoldTreeJobInput(job_id=job_id, workspace_id=auth.workspace_id)
        )
    except ScaffoldTreeJobNotFound:
        raise HTTPException(status_code=404, detail="scaffold tree job not found")
    return JobDetailResponse(
        id=job.id,
        status=job.status.value,
        ids_hash=job.ids_hash,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        tree=_serialize_tree(job.result) if job.result is not None else None,
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_scaffold_tree_job(
    job_id: UUID,
    auth: AuthDep,
    uc: CancelScaffoldTreeJobDep,
) -> JobDetailResponse:
    """Request cancellation of a pending or running scaffold tree job."""
    try:
        job = await uc.execute(
            CancelScaffoldTreeJobInput(
                job_id=job_id,
                workspace_id=auth.workspace_id,
                now=datetime.now(timezone.utc),
            )
        )
    except ScaffoldTreeJobNotFound:
        raise HTTPException(status_code=404, detail="scaffold tree job not found")
    return JobDetailResponse(
        id=job.id,
        status=job.status.value,
        ids_hash=job.ids_hash,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        tree=_serialize_tree(job.result) if job.result is not None else None,
    )
