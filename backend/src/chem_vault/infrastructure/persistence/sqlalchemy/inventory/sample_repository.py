"""SQLAlchemy repository for Sample aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.inventory.enums import ContainerType, SampleStatus
from chem_vault.domain.inventory.sample import Sample
from chem_vault.domain.shared.enums import AmountUnit, ConcentrationUnit
from chem_vault.domain.shared.value_objects import Amount, Barcode, Concentration
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import SampleModel


class SQLAlchemySampleRepository(SQLAlchemyRepository[Sample, SampleModel]):
    model_class = SampleModel

    async def find_by_batch(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> list[Sample]:
        stmt = (
            select(SampleModel)
            .where(
                SampleModel.workspace_id == workspace_id,
                SampleModel.batch_id == batch_id,
            )
            .order_by(SampleModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_location(
        self, workspace_id: uuid.UUID, location_id: uuid.UUID
    ) -> list[Sample]:
        stmt = (
            select(SampleModel)
            .where(
                SampleModel.workspace_id == workspace_id,
                SampleModel.location_id == location_id,
            )
            .order_by(SampleModel.barcode)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_barcode(
        self, workspace_id: uuid.UUID, barcode: str
    ) -> Sample | None:
        stmt = select(SampleModel).where(
            SampleModel.workspace_id == workspace_id,
            SampleModel.barcode == barcode,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_low_stock(self, workspace_id: uuid.UUID) -> list[Sample]:
        stmt = (
            select(SampleModel)
            .where(
                SampleModel.workspace_id == workspace_id,
                SampleModel.status == SampleStatus.AVAILABLE.value,
                SampleModel.low_stock_threshold.isnot(None),
                SampleModel.amount_value < SampleModel.low_stock_threshold,
            )
            .order_by(SampleModel.amount_value)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: SampleModel) -> Sample:
        concentration = None
        if model.concentration_value is not None and model.concentration_unit is not None:
            concentration = Concentration(
                value=model.concentration_value,
                unit=ConcentrationUnit(model.concentration_unit),
            )
        return Sample(
            id=model.id,
            workspace_id=model.workspace_id,
            batch_id=model.batch_id,
            barcode=Barcode(value=model.barcode),
            container_type=ContainerType(model.container_type),
            amount=Amount(value=model.amount_value, unit=AmountUnit(model.amount_unit)),
            concentration=concentration,
            solvent=model.solvent,
            status=SampleStatus(model.status),
            location_id=model.location_id,
            freeze_thaw_count=model.freeze_thaw_count,
            low_stock_threshold=model.low_stock_threshold,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Sample) -> SampleModel:
        return SampleModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            batch_id=aggregate.batch_id,
            barcode=aggregate.barcode.value,
            container_type=aggregate.container_type.value,
            amount_value=aggregate.amount.value,
            amount_unit=aggregate.amount.unit.value,
            concentration_value=aggregate.concentration.value if aggregate.concentration else None,
            concentration_unit=aggregate.concentration.unit.value if aggregate.concentration else None,
            solvent=aggregate.solvent,
            status=aggregate.status.value,
            location_id=aggregate.location_id,
            freeze_thaw_count=aggregate.freeze_thaw_count,
            low_stock_threshold=aggregate.low_stock_threshold,
            version=aggregate.version,
        )

    def _update_model(self, model: SampleModel, aggregate: Sample) -> None:
        model.amount_value = aggregate.amount.value
        model.amount_unit = aggregate.amount.unit.value
        model.concentration_value = aggregate.concentration.value if aggregate.concentration else None
        model.concentration_unit = aggregate.concentration.unit.value if aggregate.concentration else None
        model.solvent = aggregate.solvent
        model.status = aggregate.status.value
        model.location_id = aggregate.location_id
        model.freeze_thaw_count = aggregate.freeze_thaw_count
        model.low_stock_threshold = aggregate.low_stock_threshold
