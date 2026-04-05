"""SQLAlchemy repository for ReadoutData entities.

ReadoutData is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

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

    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[ReadoutData]:
        """All non-outlier readout data for a molecule, ordered by created_at desc."""
        stmt = (
            select(ReadoutDataModel)
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id == molecule_id,
                ReadoutDataModel.is_outlier == False,  # noqa: E712
            )
            .order_by(ReadoutDataModel.created_at.desc())
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_aggregated_by_molecules(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        readout_definition_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, dict[uuid.UUID, "AggregatedReadout"]]:
        """Batch query: molecule_id -> readout_def_id -> aggregated value.

        Aggregation method comes from readout_definition.aggregation setting.
        """
        from chem_vault.domain.screening_assay.activity_types import AggregatedReadout
        from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            ReadoutDefinitionModel,
        )

        if not molecule_ids or not readout_definition_ids:
            return {}

        stmt = (
            select(
                ReadoutDataModel.molecule_id,
                ReadoutDataModel.readout_definition_id,
                ReadoutDefinitionModel.name.label("readout_name"),
                ReadoutDefinitionModel.aggregation,
                ReadoutDefinitionModel.unit,
                func.avg(ReadoutDataModel.value_numeric).label("avg_val"),
                func.min(ReadoutDataModel.value_numeric).label("min_val"),
                func.max(ReadoutDataModel.value_numeric).label("max_val"),
                func.count(ReadoutDataModel.value_numeric).label("count_val"),
            )
            .join(
                ReadoutDefinitionModel,
                ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
            )
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id.in_(molecule_ids),
                ReadoutDataModel.readout_definition_id.in_(readout_definition_ids),
                ReadoutDataModel.is_outlier == False,  # noqa: E712
            )
            .group_by(
                ReadoutDataModel.molecule_id,
                ReadoutDataModel.readout_definition_id,
                ReadoutDefinitionModel.name,
                ReadoutDefinitionModel.aggregation,
                ReadoutDefinitionModel.unit,
            )
        )

        result = await self._uow.session.execute(stmt)
        rows = result.all()

        out: dict[uuid.UUID, dict[uuid.UUID, AggregatedReadout]] = {}
        for row in rows:
            agg = row.aggregation or "mean"
            if agg == "min":
                val = row.min_val
            elif agg == "max":
                val = row.max_val
            else:  # mean, none, median (approx as mean)
                val = row.avg_val

            entry = AggregatedReadout(
                readout_definition_id=row.readout_definition_id,
                readout_name=row.readout_name,
                value=val,
                qualifier=None,
                unit=row.unit,
                aggregation=agg,
                data_point_count=row.count_val,
            )
            out.setdefault(row.molecule_id, {})[row.readout_definition_id] = entry

        return out

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
