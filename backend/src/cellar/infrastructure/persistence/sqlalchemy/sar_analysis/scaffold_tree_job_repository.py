"""SQLAlchemy implementation of ScaffoldTreeJobRepository."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeEdge,
    ScaffoldTreeNode,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.models import (
    ScaffoldTreeJobModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyScaffoldTreeJobRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save(self, job: ScaffoldTreeJob) -> None:
        session = self._uow.session
        existing = await session.get(ScaffoldTreeJobModel, job.id)
        if existing is None:
            session.add(_to_model(job))
        else:
            _apply_to_model(existing, job)

    async def find_by_id(
        self, job_id: UUID, *, workspace_id: UUID
    ) -> ScaffoldTreeJob | None:
        session = self._uow.session
        stmt = select(ScaffoldTreeJobModel).where(
            ScaffoldTreeJobModel.id == job_id,
            ScaffoldTreeJobModel.workspace_id == workspace_id,
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def find_cached(
        self, *, ids_hash: str, ttl_seconds: int | None
    ) -> ScaffoldTreeResult | None:
        session = self._uow.session
        conditions = [
            ScaffoldTreeJobModel.ids_hash == ids_hash,
            ScaffoldTreeJobModel.status == ScaffoldTreeJobStatus.READY.value,
        ]
        # ttl_seconds=None → id-based cache: a ready tree for this exact member
        # set (ids_hash) never goes stale on time alone. Membership changes
        # produce a different ids_hash, so they miss naturally and recompute.
        if ttl_seconds is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
            conditions.append(ScaffoldTreeJobModel.completed_at > cutoff)
        stmt = (
            select(ScaffoldTreeJobModel)
            .where(*conditions)
            .order_by(ScaffoldTreeJobModel.completed_at.desc())
            .limit(1)
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        if model is None or model.result_json is None:
            return None
        return _deserialize_result(model.result_json)


def _to_model(job: ScaffoldTreeJob) -> ScaffoldTreeJobModel:
    return ScaffoldTreeJobModel(
        id=job.id,
        workspace_id=job.workspace_id,
        requested_by=job.requested_by,
        ids_hash=job.ids_hash,
        requested_at=job.requested_at,
        status=job.status.value,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        result_json=_serialize_result(job.result) if job.result else None,
        version=job.version,
    )


def _apply_to_model(model: ScaffoldTreeJobModel, job: ScaffoldTreeJob) -> None:
    model.status = job.status.value
    model.started_at = job.started_at
    model.completed_at = job.completed_at
    model.error_message = job.error_message
    model.result_json = _serialize_result(job.result) if job.result else None
    model.version = job.version


def _to_domain(model: ScaffoldTreeJobModel) -> ScaffoldTreeJob:
    return ScaffoldTreeJob(
        id=model.id,
        workspace_id=model.workspace_id,
        requested_by=model.requested_by,
        ids_hash=model.ids_hash,
        requested_at=model.requested_at,
        status=ScaffoldTreeJobStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_message=model.error_message,
        result=_deserialize_result(model.result_json) if model.result_json else None,
        version=model.version,
    )


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
            ScaffoldTreeEdge(
                parent_smiles=e["parent_smiles"], child_smiles=e["child_smiles"]
            )
            for e in payload.get("edges", [])
        ],
        stats=ScaffoldTreeStats(**payload.get("stats", {})),
    )
