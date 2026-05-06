"""SQLAlchemy repository for BulkRegistration aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chem_vault.domain.chemical_registration.bulk_registration import (
    BulkRegistration,
    BulkRegistrationItem,
)
from chem_vault.domain.chemical_registration.enums import (
    BulkRegistrationFileFormat,
    BulkRegistrationStatus,
)
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_models import (
    BulkRegistrationItemModel,
    BulkRegistrationModel,
)


class SQLAlchemyBulkRegistrationRepository(
    SQLAlchemyRepository[BulkRegistration, BulkRegistrationModel]
):
    model_class = BulkRegistrationModel

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[BulkRegistration]:
        stmt = (
            select(BulkRegistrationModel)
            .where(BulkRegistrationModel.workspace_id == workspace_id)
            .order_by(BulkRegistrationModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain_tracked(m) for m in models]

    async def find_by_workflow_id_in_workspace(
        self, workspace_id: uuid.UUID, workflow_id: str
    ) -> BulkRegistration | None:
        stmt = (
            select(BulkRegistrationModel)
            .where(
                BulkRegistrationModel.workspace_id == workspace_id,
                BulkRegistrationModel.workflow_id == workflow_id,
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain_tracked(model)

    async def insert_items(
        self, items: list[BulkRegistrationItem]
    ) -> None:
        """Bulk-insert per-row items, idempotent on (bulk_registration_id, row_index).

        Idempotency lets the workflow retry a chunk's persistence without
        creating duplicate rows; the unique index covers it.
        """
        if not items:
            return
        rows = [
            {
                "id": i.id,
                "bulk_registration_id": i.bulk_registration_id,
                "workspace_id": i.workspace_id,
                "row_index": i.row_index,
                "action": i.action.value,
                "success": i.success,
                "molecule_id": i.molecule_id,
                "molecule_name": i.molecule_name,
                "registration_number": i.registration_number,
                "batch_id": i.batch_id,
                "batch_number": i.batch_number,
                "error": i.error,
                "created_at": i.created_at,
            }
            for i in items
        ]
        stmt = pg_insert(BulkRegistrationItemModel).values(rows).on_conflict_do_nothing(
            index_elements=["bulk_registration_id", "row_index"]
        )
        await self._session.execute(stmt)

    async def save(self, aggregate: BulkRegistration) -> None:  # type: ignore[override]
        await super().save(aggregate)
        pending = aggregate.collect_pending_items()
        if pending:
            await self.insert_items(pending)

    # ------------------------------------------------------------------
    # Mapping: SA model -> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: BulkRegistrationModel) -> BulkRegistration:
        return BulkRegistration(
            id=model.id,
            workspace_id=model.workspace_id,
            source_file=model.source_file,
            file_format=BulkRegistrationFileFormat(model.file_format),
            submitted_by=model.submitted_by,
            submitted_at=model.submitted_at,
            workflow_id=model.workflow_id,
            status=BulkRegistrationStatus(model.status),
            total_count=model.total_count,
            registered_count=model.registered_count,
            duplicate_count=model.duplicate_count,
            error_count=model.error_count,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (INSERT)
    # ------------------------------------------------------------------

    def _to_model(self, aggregate: BulkRegistration) -> BulkRegistrationModel:
        return BulkRegistrationModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            source_file=aggregate.source_file,
            file_format=aggregate.file_format.value,
            submitted_by=aggregate.submitted_by,
            submitted_at=aggregate.submitted_at,
            workflow_id=aggregate.workflow_id,
            status=aggregate.status.value,
            total_count=aggregate.total_count,
            registered_count=aggregate.registered_count,
            duplicate_count=aggregate.duplicate_count,
            error_count=aggregate.error_count,
            completed_at=aggregate.completed_at,
            version=aggregate.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (UPDATE)
    # ------------------------------------------------------------------

    def _update_model(
        self, model: BulkRegistrationModel, aggregate: BulkRegistration
    ) -> None:
        model.status = aggregate.status.value
        model.total_count = aggregate.total_count
        model.registered_count = aggregate.registered_count
        model.duplicate_count = aggregate.duplicate_count
        model.error_count = aggregate.error_count
        model.completed_at = aggregate.completed_at
