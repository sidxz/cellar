"""SQLAlchemy implementation of RGroupDecompositionRunRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, select, update

from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.shared.errors import AuthorizationError, ConcurrencyConflictError
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import (
    RGroupAssignmentModel,
    RGroupDecompositionRunModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyRGroupDecompositionRunRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save(self, run: RGroupDecompositionRun) -> None:
        """Persist the run header (INSERT or version-checked UPDATE).

        The UPDATE is guarded on the version the aggregate was loaded with and
        bumps it; a stale writer (``rowcount == 0``) raises
        ``ConcurrencyConflictError`` rather than silently clobbering a row a
        concurrent transition (e.g. a cancel) already advanced.
        """
        session = self._uow.session
        existing = await session.get(RGroupDecompositionRunModel, run.id)
        if existing is None:
            session.add(_to_model(run))
            return
        if existing.workspace_id != run.workspace_id:
            raise AuthorizationError(
                "Cannot update RGroupDecompositionRun from a different workspace"
            )
        loaded_version = run.version
        _apply_to_model(existing, run)
        result = await session.execute(
            update(RGroupDecompositionRunModel)
            .where(
                RGroupDecompositionRunModel.id == run.id,
                RGroupDecompositionRunModel.workspace_id == run.workspace_id,
                RGroupDecompositionRunModel.version == loaded_version,
            )
            .values(version=loaded_version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            raise ConcurrencyConflictError("RGroupDecompositionRun", str(run.id))
        existing.version = loaded_version + 1

    async def find_by_id(
        self, run_id: UUID, *, workspace_id: UUID
    ) -> RGroupDecompositionRun | None:
        session = self._uow.session
        stmt = select(RGroupDecompositionRunModel).where(
            RGroupDecompositionRunModel.id == run_id,
            RGroupDecompositionRunModel.workspace_id == workspace_id,
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def find_cached(
        self, *, workspace_id: UUID, membership_hash: str, core_hash: str
    ) -> RGroupDecompositionRun | None:
        session = self._uow.session
        stmt = (
            select(RGroupDecompositionRunModel)
            .where(
                RGroupDecompositionRunModel.workspace_id == workspace_id,
                RGroupDecompositionRunModel.membership_hash == membership_hash,
                RGroupDecompositionRunModel.core_hash == core_hash,
                RGroupDecompositionRunModel.status == RGroupDecompositionRunStatus.READY.value,
            )
            .order_by(RGroupDecompositionRunModel.completed_at.desc())
            .limit(1)
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def write_assignments(
        self, run_id: UUID, assignments: list[RGroupAssignment]
    ) -> None:
        session = self._uow.session
        BATCH = 1000
        rows = [
            {"run_id": run_id, "molecule_id": a.molecule_id, "rgroups": a.rgroups}
            for a in assignments
        ]
        for i in range(0, len(rows), BATCH):
            await session.execute(insert(RGroupAssignmentModel), rows[i : i + BATCH])

    async def delete_assignments(self, run_id: UUID) -> None:
        """Remove all assignment rows for a run.

        Used by the runner to reset before recomputing, so a re-run (e.g. a
        Temporal retry) is idempotent and never collides on the
        (run_id, molecule_id) primary key.
        """
        session = self._uow.session
        await session.execute(
            sa_delete(RGroupAssignmentModel).where(RGroupAssignmentModel.run_id == run_id)
        )

    async def fetch_assignments(
        self, run_id: UUID, *, workspace_id: UUID, offset: int, limit: int
    ) -> list[RGroupAssignment]:
        session = self._uow.session
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
        models = (await session.execute(stmt)).scalars().all()
        return [
            RGroupAssignment(molecule_id=m.molecule_id, rgroups=dict(m.rgroups))
            for m in models
        ]

    async def count_assignments(self, run_id: UUID, *, workspace_id: UUID) -> int:
        session = self._uow.session
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
        return int((await session.execute(stmt)).scalar_one())


def _to_model(run: RGroupDecompositionRun) -> RGroupDecompositionRunModel:
    return RGroupDecompositionRunModel(
        id=run.id,
        workspace_id=run.workspace_id,
        requested_by=run.requested_by,
        membership_hash=run.membership_hash,
        core_smiles=run.core_smiles,
        core_hash=run.core_hash,
        requested_at=run.requested_at,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        rgroup_labels=list(run.rgroup_labels),
        matched_count=run.matched_count,
        unmatched_count=run.unmatched_count,
        total_count=run.total_count,
        version=run.version,
    )


def _apply_to_model(model: RGroupDecompositionRunModel, run: RGroupDecompositionRun) -> None:
    # version is owned by save()'s optimistic-concurrency UPDATE, not copied here.
    model.status = run.status.value
    model.started_at = run.started_at
    model.completed_at = run.completed_at
    model.error_message = run.error_message
    model.rgroup_labels = list(run.rgroup_labels)
    model.matched_count = run.matched_count
    model.unmatched_count = run.unmatched_count
    model.total_count = run.total_count


def _to_domain(model: RGroupDecompositionRunModel) -> RGroupDecompositionRun:
    return RGroupDecompositionRun(
        id=model.id,
        workspace_id=model.workspace_id,
        requested_by=model.requested_by,
        membership_hash=model.membership_hash,
        core_smiles=model.core_smiles,
        core_hash=model.core_hash,
        requested_at=model.requested_at,
        status=RGroupDecompositionRunStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_message=model.error_message,
        rgroup_labels=list(model.rgroup_labels or []),
        matched_count=model.matched_count,
        unmatched_count=model.unmatched_count,
        total_count=model.total_count,
        version=model.version,
    )
