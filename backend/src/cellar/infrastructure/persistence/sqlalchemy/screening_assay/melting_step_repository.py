"""SQLAlchemy repository for MeltingStep entities.

Not an AggregateRoot (no events), so a standalone repo like the measured-curve one;
``update`` carries its own version check.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update

from cellar.domain.screening_assay.melting_step import (
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.domain.shared.errors import ConflictError
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    MeltingStepModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyMeltingStepRepository:
    """Persists MeltingStep entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save_bulk(self, steps: list[MeltingStep]) -> None:
        self._uow.session.add_all([self._to_model(s) for s in steps])

    async def add(self, step: MeltingStep) -> None:
        self._uow.session.add(self._to_model(step))

    async def update(self, step: MeltingStep, *, expected_version: int) -> None:
        stmt = (
            update(MeltingStepModel)
            .where(
                MeltingStepModel.id == step.id,
                MeltingStepModel.workspace_id == step.workspace_id,
                MeltingStepModel.version == expected_version,
            )
            .values(
                value=step.value,
                status=step.status.value,
                reason=step.reason,
                changed_by=step.changed_by,
                changed_at=step.changed_at,
                version=step.version,
                updated_at=step.updated_at,
            )
        )  # default session sync keeps an already-loaded row current for later reads
        result = await self._uow.session.execute(stmt)
        if not result.rowcount:
            raise ConflictError(
                "This melting step was changed by someone else. Reload and try again."
            )

    async def find_by_id(self, workspace_id: uuid.UUID, step_id: uuid.UUID) -> MeltingStep | None:
        stmt = select(MeltingStepModel).where(
            MeltingStepModel.workspace_id == workspace_id, MeltingStepModel.id == step_id
        )
        model = (await self._uow.session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> list[MeltingStep]:
        stmt = (
            select(MeltingStepModel)
            .where(
                MeltingStepModel.workspace_id == workspace_id, MeltingStepModel.run_id == run_id
            )
            .order_by(
                MeltingStepModel.well_id, MeltingStepModel.channel_key, MeltingStepModel.value
            )
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def delete_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int:
        stmt = delete(MeltingStepModel).where(
            MeltingStepModel.workspace_id == workspace_id, MeltingStepModel.run_id == run_id
        )
        result = await self._uow.session.execute(stmt)
        return result.rowcount or 0

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: MeltingStepModel) -> MeltingStep:
        return MeltingStep(
            id=model.id,
            workspace_id=model.workspace_id,
            run_id=model.run_id,
            well_id=model.well_id,
            channel_key=model.channel_key,
            source=MeltingStepSource(model.source),
            value=model.value,
            instrument_value=model.instrument_value,
            instrument_label=model.instrument_label,
            status=MeltingStepStatus(model.status),
            reason=model.reason,
            changed_by=model.changed_by,
            changed_at=model.changed_at,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: MeltingStep) -> MeltingStepModel:
        return MeltingStepModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            run_id=entity.run_id,
            well_id=entity.well_id,
            channel_key=entity.channel_key,
            source=entity.source.value,
            value=entity.value,
            instrument_value=entity.instrument_value,
            instrument_label=entity.instrument_label,
            status=entity.status.value,
            reason=entity.reason,
            changed_by=entity.changed_by,
            changed_at=entity.changed_at,
            version=entity.version,
        )
