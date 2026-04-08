"""SQLAlchemy repository for Batch aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from chem_vault.domain.inventory.batch import Batch
from chem_vault.domain.inventory.enums import BatchSource
from chem_vault.domain.shared.enums import AmountUnit, ConcentrationUnit, LightCondition
from chem_vault.domain.shared.value_objects import Amount, BatchNumber, Concentration, StorageCondition
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel


class SQLAlchemyBatchRepository(SQLAlchemyRepository[Batch, BatchModel]):
    model_class = BatchModel

    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[Batch]:
        stmt = (
            select(BatchModel)
            .where(
                BatchModel.workspace_id == workspace_id,
                BatchModel.molecule_id == molecule_id,
            )
            .order_by(BatchModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_batch_number(
        self, workspace_id: uuid.UUID, batch_number: str
    ) -> Batch | None:
        stmt = select(BatchModel).where(
            BatchModel.workspace_id == workspace_id,
            BatchModel.batch_number == batch_number,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def next_batch_number(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> BatchNumber:
        stmt = (
            select(func.count())
            .select_from(BatchModel)
            .where(
                BatchModel.workspace_id == workspace_id,
                BatchModel.molecule_id == molecule_id,
            )
        )
        result = await self._session.execute(stmt)
        count = result.scalar() or 0
        return BatchNumber(value=f"B-{count + 1:03d}")

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: BatchModel) -> Batch:
        concentration = None
        if model.concentration_value is not None and model.concentration_unit is not None:
            concentration = Concentration(
                value=model.concentration_value,
                unit=ConcentrationUnit(model.concentration_unit),
            )
        storage_conditions = None
        if model.storage_temperature_celsius is not None:
            storage_conditions = StorageCondition(
                temperature_celsius=model.storage_temperature_celsius,
                relative_humidity_percent=model.storage_humidity_percent,
                light_condition=LightCondition(model.storage_light_condition) if model.storage_light_condition else None,
            )
        return Batch(
            id=model.id,
            workspace_id=model.workspace_id,
            molecule_id=model.molecule_id,
            batch_number=BatchNumber(value=model.batch_number),
            salt_entry_id=model.salt_entry_id,
            salt_name=model.salt_name,
            salt_smiles=model.salt_smiles,
            salt_stoichiometry=model.salt_stoichiometry,
            formula_weight=model.formula_weight,
            purity=model.purity,
            amount=Amount(value=model.amount_value, unit=AmountUnit(model.amount_unit)),
            concentration=concentration,
            source=BatchSource(model.source),
            supplier_org_id=model.supplier_org_id,
            vendor_catalog_number=model.vendor_catalog_number,
            vendor_lot_number=model.vendor_lot_number,
            chemist=model.chemist,
            synthesis_date=model.synthesis_date,
            expiry_date=model.expiry_date,
            notebook_reference=model.notebook_reference,
            storage_conditions=storage_conditions,
            storage_conditions_notes=model.storage_conditions_notes,
            appearance=model.appearance,
            custom_fields=model.custom_fields,
            synthesis_route_id=model.synthesis_route_id,
            synthesis_step_id=model.synthesis_step_id,
            synthesis_request_id=model.synthesis_request_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Batch) -> BatchModel:
        return BatchModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            molecule_id=aggregate.molecule_id,
            batch_number=aggregate.batch_number.value,
            salt_entry_id=aggregate.salt_entry_id,
            salt_name=aggregate.salt_name,
            salt_smiles=aggregate.salt_smiles,
            salt_stoichiometry=aggregate.salt_stoichiometry,
            formula_weight=aggregate.formula_weight,
            purity=aggregate.purity,
            amount_value=aggregate.amount.value,
            amount_unit=aggregate.amount.unit.value,
            concentration_value=aggregate.concentration.value if aggregate.concentration else None,
            concentration_unit=aggregate.concentration.unit.value if aggregate.concentration else None,
            source=aggregate.source.value,
            supplier_org_id=aggregate.supplier_org_id,
            vendor_catalog_number=aggregate.vendor_catalog_number,
            vendor_lot_number=aggregate.vendor_lot_number,
            chemist=aggregate.chemist,
            synthesis_date=aggregate.synthesis_date,
            expiry_date=aggregate.expiry_date,
            notebook_reference=aggregate.notebook_reference,
            storage_temperature_celsius=aggregate.storage_conditions.temperature_celsius if aggregate.storage_conditions else None,
            storage_humidity_percent=aggregate.storage_conditions.relative_humidity_percent if aggregate.storage_conditions else None,
            storage_light_condition=aggregate.storage_conditions.light_condition.value if aggregate.storage_conditions and aggregate.storage_conditions.light_condition else None,
            storage_conditions_notes=aggregate.storage_conditions_notes,
            appearance=aggregate.appearance,
            custom_fields=aggregate.custom_fields,
            synthesis_route_id=aggregate.synthesis_route_id,
            synthesis_step_id=aggregate.synthesis_step_id,
            synthesis_request_id=aggregate.synthesis_request_id,
            version=aggregate.version,
        )

    def _update_model(self, model: BatchModel, aggregate: Batch) -> None:
        model.molecule_id = aggregate.molecule_id
        model.salt_entry_id = aggregate.salt_entry_id
        model.salt_name = aggregate.salt_name
        model.salt_smiles = aggregate.salt_smiles
        model.salt_stoichiometry = aggregate.salt_stoichiometry
        model.formula_weight = aggregate.formula_weight
        model.purity = aggregate.purity
        model.amount_value = aggregate.amount.value
        model.amount_unit = aggregate.amount.unit.value
        model.concentration_value = aggregate.concentration.value if aggregate.concentration else None
        model.concentration_unit = aggregate.concentration.unit.value if aggregate.concentration else None
        model.source = aggregate.source.value
        model.supplier_org_id = aggregate.supplier_org_id
        model.vendor_catalog_number = aggregate.vendor_catalog_number
        model.vendor_lot_number = aggregate.vendor_lot_number
        model.chemist = aggregate.chemist
        model.synthesis_date = aggregate.synthesis_date
        model.expiry_date = aggregate.expiry_date
        model.notebook_reference = aggregate.notebook_reference
        model.synthesis_route_id = aggregate.synthesis_route_id
        model.synthesis_step_id = aggregate.synthesis_step_id
        model.synthesis_request_id = aggregate.synthesis_request_id
        model.appearance = aggregate.appearance
        model.custom_fields = aggregate.custom_fields
        model.storage_conditions_notes = aggregate.storage_conditions_notes
        if aggregate.storage_conditions:
            model.storage_temperature_celsius = aggregate.storage_conditions.temperature_celsius
            model.storage_humidity_percent = aggregate.storage_conditions.relative_humidity_percent
            model.storage_light_condition = aggregate.storage_conditions.light_condition.value if aggregate.storage_conditions.light_condition else None
        else:
            model.storage_temperature_celsius = None
            model.storage_humidity_percent = None
            model.storage_light_condition = None
