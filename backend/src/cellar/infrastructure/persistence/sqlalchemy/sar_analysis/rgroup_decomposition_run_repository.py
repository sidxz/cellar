"""SQLAlchemy implementation of RGroupDecompositionRunRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, select

from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import (
    RGroupAssignmentModel,
    RGroupDecompositionRunModel,
)


class SQLAlchemyRGroupDecompositionRunRepository(
    SQLAlchemyRepository[RGroupDecompositionRun, RGroupDecompositionRunModel]
):
    model_class = RGroupDecompositionRunModel

    def _to_domain(self, model: RGroupDecompositionRunModel) -> RGroupDecompositionRun:
        return RGroupDecompositionRun(
            id=model.id,
            workspace_id=model.workspace_id,
            requested_by=model.requested_by,
            membership_hash=model.membership_hash,
            core_smiles=model.core_smiles,
            core_hash=model.core_hash,
            requested_at=model.requested_at,
            status=AsyncJobStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            rgroup_labels=list(model.rgroup_labels or []),
            matched_count=model.matched_count,
            unmatched_count=model.unmatched_count,
            total_count=model.total_count,
            version=model.version,
        )

    def _to_model(self, aggregate: RGroupDecompositionRun) -> RGroupDecompositionRunModel:
        return RGroupDecompositionRunModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requested_by=aggregate.requested_by,
            membership_hash=aggregate.membership_hash,
            core_smiles=aggregate.core_smiles,
            core_hash=aggregate.core_hash,
            requested_at=aggregate.requested_at,
            status=aggregate.status.value,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            error_message=aggregate.error_message,
            rgroup_labels=list(aggregate.rgroup_labels),
            matched_count=aggregate.matched_count,
            unmatched_count=aggregate.unmatched_count,
            total_count=aggregate.total_count,
            version=aggregate.version,
        )

    def _update_model(
        self, model: RGroupDecompositionRunModel, aggregate: RGroupDecompositionRun
    ) -> None:
        # version is owned by the base save()'s optimistic-concurrency UPDATE.
        model.status = aggregate.status.value
        model.started_at = aggregate.started_at
        model.completed_at = aggregate.completed_at
        model.error_message = aggregate.error_message
        model.rgroup_labels = list(aggregate.rgroup_labels)
        model.matched_count = aggregate.matched_count
        model.unmatched_count = aggregate.unmatched_count
        model.total_count = aggregate.total_count

    async def find_cached(
        self, *, workspace_id: UUID, membership_hash: str, core_hash: str
    ) -> RGroupDecompositionRun | None:
        stmt = (
            select(RGroupDecompositionRunModel)
            .where(
                RGroupDecompositionRunModel.workspace_id == workspace_id,
                RGroupDecompositionRunModel.membership_hash == membership_hash,
                RGroupDecompositionRunModel.core_hash == core_hash,
                RGroupDecompositionRunModel.status == AsyncJobStatus.READY.value,
            )
            .order_by(RGroupDecompositionRunModel.completed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def write_assignments(
        self, run_id: UUID, assignments: list[RGroupAssignment]
    ) -> None:
        batch = 1000
        rows = [
            {"run_id": run_id, "molecule_id": a.molecule_id, "rgroups": a.rgroups}
            for a in assignments
        ]
        for i in range(0, len(rows), batch):
            await self._session.execute(insert(RGroupAssignmentModel), rows[i : i + batch])

    async def delete_assignments(self, run_id: UUID) -> None:
        """Remove all assignment rows for a run, so a re-run (e.g. a Temporal
        retry) is idempotent and never collides on the (run_id, molecule_id) PK."""
        await self._session.execute(
            sa_delete(RGroupAssignmentModel).where(RGroupAssignmentModel.run_id == run_id)
        )

    async def fetch_assignments(
        self, run_id: UUID, *, workspace_id: UUID, offset: int, limit: int
    ) -> list[RGroupAssignment]:
        stmt = (
            select(RGroupAssignmentModel)
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
            )
            .order_by(RGroupAssignmentModel.molecule_id)
            .offset(offset)
            .limit(limit)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [
            RGroupAssignment(molecule_id=m.molecule_id, rgroups=dict(m.rgroups))
            for m in models
        ]

    async def count_assignments(self, run_id: UUID, *, workspace_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(RGroupAssignmentModel)
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())
