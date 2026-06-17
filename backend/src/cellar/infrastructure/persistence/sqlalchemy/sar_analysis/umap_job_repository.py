"""SQLAlchemy implementation of UmapJobRepository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from cellar.domain.sar_analysis.umap_job import UmapJob
from cellar.domain.sar_analysis.umap_types import (
    ClusterAssignment,
    RepresentativePick,
    UmapPoint,
    UmapResult,
)
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.umap_job_model import (
    UmapJobModel,
)


def _encode_result(result: UmapResult) -> dict[str, Any]:
    return {
        "points": [{"molecule_id": str(p.molecule_id), "x": p.x, "y": p.y} for p in result.points],
        "clusters": [
            {"molecule_id": str(c.molecule_id), "cluster_id": c.cluster_id}
            for c in result.clusters
        ],
        "representatives": [
            {"molecule_id": str(r.molecule_id), "cluster_id": r.cluster_id}
            for r in result.representatives
        ],
        "cluster_count": result.cluster_count,
        "picker": result.picker,
        "picker_params": result.picker_params,
        "skipped_molecule_ids": [str(m) for m in result.skipped_molecule_ids],
    }


def _decode_result(payload: dict[str, Any]) -> UmapResult:
    return UmapResult(
        points=[
            UmapPoint(molecule_id=UUID(p["molecule_id"]), x=p["x"], y=p["y"])
            for p in payload["points"]
        ],
        clusters=[
            ClusterAssignment(molecule_id=UUID(c["molecule_id"]), cluster_id=c["cluster_id"])
            for c in payload["clusters"]
        ],
        representatives=[
            RepresentativePick(molecule_id=UUID(r["molecule_id"]), cluster_id=r["cluster_id"])
            for r in payload["representatives"]
        ],
        cluster_count=payload["cluster_count"],
        picker=payload["picker"],
        picker_params=payload["picker_params"],
        skipped_molecule_ids=[UUID(m) for m in payload.get("skipped_molecule_ids", [])],
    )


class SQLAlchemyUmapJobRepository(SQLAlchemyRepository[UmapJob, UmapJobModel]):
    model_class = UmapJobModel

    def _to_domain(self, model: UmapJobModel) -> UmapJob:
        return UmapJob(
            id=model.id,
            workspace_id=model.workspace_id,
            requested_by=model.requested_by,
            ids_hash=model.ids_hash,
            picker=model.picker,
            picker_params=model.picker_params,
            picker_param_hash=model.picker_param_hash,
            requested_at=model.requested_at,
            status=AsyncJobStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            result=_decode_result(model.result_json) if model.result_json else None,
            version=model.version,
        )

    def _to_model(self, aggregate: UmapJob) -> UmapJobModel:
        return UmapJobModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requested_by=aggregate.requested_by,
            ids_hash=aggregate.ids_hash,
            picker=aggregate.picker,
            picker_params=aggregate.picker_params,
            picker_param_hash=aggregate.picker_param_hash,
            status=aggregate.status.value,
            result_json=_encode_result(aggregate.result) if aggregate.result else None,
            error_message=aggregate.error_message,
            requested_at=aggregate.requested_at,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            version=aggregate.version,
        )

    def _update_model(self, model: UmapJobModel, aggregate: UmapJob) -> None:
        # version is owned by the base save()'s optimistic-concurrency UPDATE.
        model.status = aggregate.status.value
        model.started_at = aggregate.started_at
        model.completed_at = aggregate.completed_at
        model.error_message = aggregate.error_message
        model.result_json = _encode_result(aggregate.result) if aggregate.result else None

    async def find_cached(
        self,
        *,
        workspace_id: UUID,
        ids_hash: str,
        picker: str,
        picker_param_hash: str,
        ttl_seconds: int,
    ) -> UmapJob | None:
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=ttl_seconds)
        stmt = (
            select(UmapJobModel)
            .where(
                UmapJobModel.workspace_id == workspace_id,
                UmapJobModel.ids_hash == ids_hash,
                UmapJobModel.picker == picker,
                UmapJobModel.picker_param_hash == picker_param_hash,
                UmapJobModel.status == AsyncJobStatus.READY.value,
                UmapJobModel.completed_at >= cutoff,
            )
            .order_by(UmapJobModel.completed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_compatible_for_pick(
        self,
        *,
        workspace_id: UUID,
        ids_hash: str,
        threshold: float,
        ttl_seconds: int,
    ) -> UmapJob | None:
        """Find any READY job with matching ids_hash + threshold.

        Used by the partial-cache path: if we have UMAP coords + Butina clusters
        for the same compound set at the same threshold, we can reuse them and
        only re-run the picker (MaxMin in particular skips the expensive UMAP
        step). The matched job may have any picker / N.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=ttl_seconds)
        threshold_expr = UmapJobModel.picker_params["threshold"].as_float()
        stmt = (
            select(UmapJobModel)
            .where(
                UmapJobModel.workspace_id == workspace_id,
                UmapJobModel.ids_hash == ids_hash,
                threshold_expr == threshold,
                UmapJobModel.status == AsyncJobStatus.READY.value,
                UmapJobModel.completed_at >= cutoff,
            )
            .order_by(UmapJobModel.completed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None
