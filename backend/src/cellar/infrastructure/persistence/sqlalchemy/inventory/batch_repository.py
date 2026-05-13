"""SQLAlchemy repository for Batch aggregates."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.sql import expression

from cellar.domain.shared.pagination import PageResult
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import BatchNumber
from cellar.infrastructure.persistence.sqlalchemy.inventory._vo_mappers import (
    amount_from_columns,
    amount_to_columns,
    concentration_from_columns,
    concentration_to_columns,
    storage_from_columns,
    storage_to_columns,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel, SampleModel


class SQLAlchemyBatchRepository(SQLAlchemyRepository[Batch, BatchModel]):
    model_class = BatchModel

    async def find_by_ids(self, workspace_id: uuid.UUID, ids: list[uuid.UUID]) -> list[Batch]:
        """Bulk-fetch batches by IDs, scoped to workspace."""
        if not ids:
            return []
        stmt = select(BatchModel).where(
            BatchModel.workspace_id == workspace_id,
            BatchModel.id.in_(ids),
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

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
        # Batch number = {molecule_reg_number}-{seq} (e.g., CV-00001-001).
        # Count existing batches for this molecule to determine the next seq.

        # 1. Get molecule registration number
        mol_stmt = select(MoleculeModel.registration_number).where(MoleculeModel.id == molecule_id)
        mol_result = await self._session.execute(mol_stmt)
        reg_number = mol_result.scalar_one()

        # 2. Count existing batches for this molecule
        count_stmt = (
            select(func.count())
            .select_from(BatchModel)
            .where(
                BatchModel.workspace_id == workspace_id,
                BatchModel.molecule_id == molecule_id,
            )
        )
        count_result = await self._session.execute(count_stmt)
        count = count_result.scalar() or 0

        return BatchNumber(value=f"{reg_number}-{count + 1:03d}")

    # ------------------------------------------------------------------
    # Global list (read-model query — returns flat dicts, not aggregates)
    # ------------------------------------------------------------------

    @staticmethod
    def _escape_like(value: str) -> str:
        """Escape special LIKE/ILIKE characters."""
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    async def list_global(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None = None,
        sources: list[str] | None = None,
        expiring_within_days: int | None = None,
        cursor: uuid.UUID | None = None,
        limit: int = 50,
    ) -> PageResult[dict]:
        # Sample stats subquery: count + any-low-stock per batch
        sample_sub = (
            select(
                SampleModel.batch_id,
                func.count().label("sample_count"),
                func.bool_or(
                    case(
                        (
                            (SampleModel.low_stock_threshold.isnot(None))
                            & (SampleModel.amount_value < SampleModel.low_stock_threshold),
                            expression.true(),
                        ),
                        else_=expression.false(),
                    )
                ).label("has_low_stock_sample"),
            )
            .where(SampleModel.workspace_id == workspace_id)
            .group_by(SampleModel.batch_id)
            .subquery("sample_stats")
        )

        stmt = (
            select(
                BatchModel.id,
                BatchModel.batch_number,
                BatchModel.molecule_id,
                MoleculeModel.name.label("molecule_name"),
                MoleculeModel.registration_number.label("molecule_registration_number"),
                BatchModel.source,
                BatchModel.amount_value,
                BatchModel.amount_unit,
                BatchModel.purity,
                BatchModel.salt_name,
                BatchModel.appearance,
                BatchModel.expiry_date,
                func.coalesce(sample_sub.c.sample_count, 0).label("sample_count"),
                func.coalesce(sample_sub.c.has_low_stock_sample, expression.false()).label(
                    "has_low_stock_sample"
                ),
                BatchModel.created_at,
            )
            .join(MoleculeModel, BatchModel.molecule_id == MoleculeModel.id)
            .outerjoin(sample_sub, BatchModel.id == sample_sub.c.batch_id)
            .where(BatchModel.workspace_id == workspace_id)
        )

        # --- filters ---
        if search:
            pattern = f"%{self._escape_like(search)}%"
            stmt = stmt.where(
                or_(
                    BatchModel.batch_number.ilike(pattern),
                    MoleculeModel.name.ilike(pattern),
                    MoleculeModel.registration_number.ilike(pattern),
                )
            )

        if sources:
            stmt = stmt.where(BatchModel.source.in_(sources))

        if expiring_within_days is not None:
            deadline = date.today() + timedelta(days=expiring_within_days)
            stmt = stmt.where(
                BatchModel.expiry_date.isnot(None),
                BatchModel.expiry_date <= deadline,
            )

        # --- cursor pagination (keyset on created_at DESC, id DESC) ---
        if cursor is not None:
            # Look up the cursor row's created_at so we can do a proper keyset
            cursor_sub = (
                select(BatchModel.created_at).where(BatchModel.id == cursor).scalar_subquery()
            )
            stmt = stmt.where(
                (BatchModel.created_at < cursor_sub)
                | ((BatchModel.created_at == cursor_sub) & (BatchModel.id < cursor))
            )

        stmt = stmt.order_by(BatchModel.created_at.desc(), BatchModel.id.desc())

        # Fetch limit + 1 to detect next page
        stmt = stmt.limit(limit + 1)

        result = await self._session.execute(stmt)
        rows = result.mappings().all()

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [dict(row) for row in page_rows]
        next_cursor = str(items[-1]["id"]) if has_next and items else None

        return PageResult(items=items, next_cursor=next_cursor)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: BatchModel) -> Batch:
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
            amount=amount_from_columns(model),
            concentration=concentration_from_columns(model),
            source=BatchSource(model.source),
            supplier_org_id=model.supplier_org_id,
            vendor_catalog_number=model.vendor_catalog_number,
            vendor_lot_number=model.vendor_lot_number,
            chemist=model.chemist,
            synthesis_date=model.synthesis_date,
            expiry_date=model.expiry_date,
            notebook_reference=model.notebook_reference,
            storage_conditions=storage_from_columns(model),
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
            **amount_to_columns(aggregate.amount),
            **concentration_to_columns(aggregate.concentration),
            source=aggregate.source.value,
            supplier_org_id=aggregate.supplier_org_id,
            vendor_catalog_number=aggregate.vendor_catalog_number,
            vendor_lot_number=aggregate.vendor_lot_number,
            chemist=aggregate.chemist,
            synthesis_date=aggregate.synthesis_date,
            expiry_date=aggregate.expiry_date,
            notebook_reference=aggregate.notebook_reference,
            **storage_to_columns(aggregate.storage_conditions),
            storage_conditions_notes=aggregate.storage_conditions_notes,
            appearance=aggregate.appearance,
            custom_fields=aggregate.custom_fields,
            synthesis_route_id=aggregate.synthesis_route_id,
            synthesis_step_id=aggregate.synthesis_step_id,
            synthesis_request_id=aggregate.synthesis_request_id,
            version=aggregate.version,
        )

    def _update_model(self, model: BatchModel, aggregate: Batch) -> None:
        model.batch_number = aggregate.batch_number.value
        model.molecule_id = aggregate.molecule_id
        model.salt_entry_id = aggregate.salt_entry_id
        model.salt_name = aggregate.salt_name
        model.salt_smiles = aggregate.salt_smiles
        model.salt_stoichiometry = aggregate.salt_stoichiometry
        model.formula_weight = aggregate.formula_weight
        model.purity = aggregate.purity
        for k, v in amount_to_columns(aggregate.amount).items():
            setattr(model, k, v)
        for k, v in concentration_to_columns(aggregate.concentration).items():
            setattr(model, k, v)
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
            model.storage_light_condition = (
                aggregate.storage_conditions.light_condition.value
                if aggregate.storage_conditions.light_condition
                else None
            )
        else:
            model.storage_temperature_celsius = None
            model.storage_humidity_percent = None
            model.storage_light_condition = None
