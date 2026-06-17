"""SQLAlchemy implementation of ScaffoldTreeJobRepository."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeEdge,
    ScaffoldTreeNode,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.models import (
    ScaffoldTreeJobModel,
)


class SQLAlchemyScaffoldTreeJobRepository(
    SQLAlchemyRepository[ScaffoldTreeJob, ScaffoldTreeJobModel]
):
    model_class = ScaffoldTreeJobModel

    def _to_domain(self, model: ScaffoldTreeJobModel) -> ScaffoldTreeJob:
        return ScaffoldTreeJob(
            id=model.id,
            workspace_id=model.workspace_id,
            requested_by=model.requested_by,
            ids_hash=model.ids_hash,
            requested_at=model.requested_at,
            status=AsyncJobStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            result=_deserialize_result(model.result_json) if model.result_json else None,
            version=model.version,
        )

    def _to_model(self, aggregate: ScaffoldTreeJob) -> ScaffoldTreeJobModel:
        return ScaffoldTreeJobModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requested_by=aggregate.requested_by,
            ids_hash=aggregate.ids_hash,
            requested_at=aggregate.requested_at,
            status=aggregate.status.value,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            error_message=aggregate.error_message,
            result_json=_serialize_result(aggregate.result) if aggregate.result else None,
            version=aggregate.version,
        )

    def _update_model(self, model: ScaffoldTreeJobModel, aggregate: ScaffoldTreeJob) -> None:
        # version is owned by the base save()'s optimistic-concurrency UPDATE.
        model.status = aggregate.status.value
        model.started_at = aggregate.started_at
        model.completed_at = aggregate.completed_at
        model.error_message = aggregate.error_message
        model.result_json = _serialize_result(aggregate.result) if aggregate.result else None

    async def find_cached(
        self, *, ids_hash: str, ttl_seconds: int | None
    ) -> ScaffoldTreeResult | None:
        conditions = [
            ScaffoldTreeJobModel.ids_hash == ids_hash,
            ScaffoldTreeJobModel.status == AsyncJobStatus.READY.value,
        ]
        # ttl_seconds=None → id-based cache: a ready tree for this exact member
        # set (ids_hash) never goes stale on time alone. Membership changes
        # produce a different ids_hash, so they miss naturally and recompute.
        if ttl_seconds is not None:
            cutoff = datetime.now(UTC) - timedelta(seconds=ttl_seconds)
            conditions.append(ScaffoldTreeJobModel.completed_at > cutoff)
        stmt = (
            select(ScaffoldTreeJobModel)
            .where(*conditions)
            .order_by(ScaffoldTreeJobModel.completed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None or model.result_json is None:
            return None
        return _deserialize_result(model.result_json)


def _serialize_result(result: ScaffoldTreeResult) -> dict:
    return {
        "nodes": [
            {
                "scaffold_smiles": n.scaffold_smiles,
                "molecule_ids": [str(mid) for mid in n.molecule_ids],
                "molecule_count": n.molecule_count,
                "subtree_molecule_count": n.subtree_molecule_count,
            }
            for n in result.nodes
        ],
        "edges": [
            {"parent_smiles": e.parent_smiles, "child_smiles": e.child_smiles}
            for e in result.edges
        ],
        "stats": dataclasses.asdict(result.stats),
    }


def _deserialize_result(payload: dict) -> ScaffoldTreeResult:
    return ScaffoldTreeResult(
        nodes=[
            ScaffoldTreeNode(
                scaffold_smiles=n["scaffold_smiles"],
                molecule_ids=[uuid.UUID(mid) for mid in n["molecule_ids"]],
                molecule_count=n["molecule_count"],
                subtree_molecule_count=n["subtree_molecule_count"],
            )
            for n in payload.get("nodes", [])
        ],
        edges=[
            ScaffoldTreeEdge(parent_smiles=e["parent_smiles"], child_smiles=e["child_smiles"])
            for e in payload.get("edges", [])
        ],
        stats=ScaffoldTreeStats(**payload.get("stats", {})),
    )
