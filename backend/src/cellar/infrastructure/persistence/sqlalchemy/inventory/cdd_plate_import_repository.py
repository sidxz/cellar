"""SQLAlchemy repository for CddPlateImport aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.inventory.cdd_plate_import import CddPlateImport
from cellar.domain.inventory.enums import CddPlateImportStatus
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_import_models import (
    CddPlateImportModel,
)


class SQLAlchemyCddPlateImportRepository(
    SQLAlchemyRepository[CddPlateImport, CddPlateImportModel]
):
    model_class = CddPlateImportModel

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> CddPlateImport | None:
        stmt = select(CddPlateImportModel).where(
            CddPlateImportModel.workspace_id == workspace_id,
            CddPlateImportModel.id == id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_by_workflow_id_in_workspace(
        self, workspace_id: uuid.UUID, workflow_id: str
    ) -> CddPlateImport | None:
        stmt = select(CddPlateImportModel).where(
            CddPlateImportModel.workspace_id == workspace_id,
            CddPlateImportModel.workflow_id == workflow_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[CddPlateImport]:
        stmt = (
            select(CddPlateImportModel)
            .where(CddPlateImportModel.workspace_id == workspace_id)
            .order_by(CddPlateImportModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain_tracked(m) for m in models]

    # ------------------------------------------------------------------
    # Mapping: SA model -> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: CddPlateImportModel) -> CddPlateImport:
        return CddPlateImport(
            id=model.id,
            workspace_id=model.workspace_id,
            cdd_vault_id=model.cdd_vault_id,
            status=CddPlateImportStatus(model.status),
            workflow_id=model.workflow_id,
            total_count=model.total_count,
            plates_registered=model.plates_registered,
            plates_duplicate=model.plates_duplicate,
            plates_error=model.plates_error,
            wells_mapped=model.wells_mapped,
            wells_unresolved=model.wells_unresolved,
            last_processed_offset=model.last_processed_offset,
            submitted_by=model.submitted_by,
            submitted_at=model.submitted_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (INSERT)
    # ------------------------------------------------------------------

    def _to_model(self, aggregate: CddPlateImport) -> CddPlateImportModel:
        return CddPlateImportModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            cdd_vault_id=aggregate.cdd_vault_id,
            status=aggregate.status.value,
            workflow_id=aggregate.workflow_id,
            total_count=aggregate.total_count,
            plates_registered=aggregate.plates_registered,
            plates_duplicate=aggregate.plates_duplicate,
            plates_error=aggregate.plates_error,
            wells_mapped=aggregate.wells_mapped,
            wells_unresolved=aggregate.wells_unresolved,
            last_processed_offset=aggregate.last_processed_offset,
            submitted_by=aggregate.submitted_by,
            submitted_at=aggregate.submitted_at,
            completed_at=aggregate.completed_at,
            version=aggregate.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (UPDATE)
    # ------------------------------------------------------------------

    def _update_model(self, model: CddPlateImportModel, aggregate: CddPlateImport) -> None:
        model.status = aggregate.status.value
        model.workflow_id = aggregate.workflow_id
        model.total_count = aggregate.total_count
        model.plates_registered = aggregate.plates_registered
        model.plates_duplicate = aggregate.plates_duplicate
        model.plates_error = aggregate.plates_error
        model.wells_mapped = aggregate.wells_mapped
        model.wells_unresolved = aggregate.wells_unresolved
        model.last_processed_offset = aggregate.last_processed_offset
        model.completed_at = aggregate.completed_at
