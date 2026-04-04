"""SQLAlchemy repository for ReadoutData entities.

ReadoutData is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.shared.enums import Qualifier
from chem_vault.domain.shared.value_objects import QualifiedValue
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDataModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyReadoutDataRepository:
    """Persists ReadoutData entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_by_id(self, id: uuid.UUID) -> ReadoutData | None:
        model = await self._uow.session.get(ReadoutDataModel, id)
        return self._to_domain(model) if model else None

    async def find_by_run(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[ReadoutData]:
        stmt = (
            select(ReadoutDataModel)
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.run_id == run_id,
            )
            .order_by(ReadoutDataModel.created_at)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, entity: ReadoutData) -> None:
        model = self._to_model(entity)
        await self._uow.session.merge(model)

    async def save_bulk(self, entities: list[ReadoutData]) -> None:
        """Bulk insert readout data points."""
        models = [self._to_model(e) for e in entities]
        self._uow.session.add_all(models)

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(ReadoutDataModel).where(
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.id == id,
        )
        await self._uow.session.execute(stmt)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: ReadoutDataModel) -> ReadoutData:
        value: QualifiedValue | None = None
        if model.value_numeric is not None:
            value = QualifiedValue(
                value=model.value_numeric,
                qualifier=(
                    Qualifier(model.value_qualifier)
                    if model.value_qualifier
                    else Qualifier.EQUAL
                ),
            )
        return ReadoutData(
            id=model.id,
            workspace_id=model.workspace_id,
            run_id=model.run_id,
            well_id=model.well_id,
            molecule_id=model.molecule_id,
            batch_id=model.batch_id,
            readout_definition_id=model.readout_definition_id,
            value=value,
            value_text=model.value_text,
            is_outlier=model.is_outlier,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: ReadoutData) -> ReadoutDataModel:
        return ReadoutDataModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            run_id=entity.run_id,
            well_id=entity.well_id,
            molecule_id=entity.molecule_id,
            batch_id=entity.batch_id,
            readout_definition_id=entity.readout_definition_id,
            value_numeric=entity.value.value if entity.value else None,
            value_qualifier=entity.value.qualifier.value if entity.value else None,
            value_text=entity.value_text,
            is_outlier=entity.is_outlier,
        )
