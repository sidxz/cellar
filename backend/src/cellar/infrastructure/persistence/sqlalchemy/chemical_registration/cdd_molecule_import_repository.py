"""SQLAlchemy repository for CddMoleculeImport aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from cellar.domain.chemical_registration.enums import (
    CddImportMode,
    CddMoleculeImportStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)

from .cdd_molecule_import_models import (
    CddMoleculeImportModel,
)


class SQLAlchemyCddMoleculeImportRepository(
    SQLAlchemyRepository[CddMoleculeImport, CddMoleculeImportModel]
):
    model_class = CddMoleculeImportModel

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> CddMoleculeImport | None:
        stmt = select(CddMoleculeImportModel).where(
            CddMoleculeImportModel.workspace_id == workspace_id,
            CddMoleculeImportModel.id == id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_by_workflow_id_in_workspace(
        self, workspace_id: uuid.UUID, workflow_id: str
    ) -> CddMoleculeImport | None:
        stmt = select(CddMoleculeImportModel).where(
            CddMoleculeImportModel.workspace_id == workspace_id,
            CddMoleculeImportModel.workflow_id == workflow_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[CddMoleculeImport]:
        stmt = (
            select(CddMoleculeImportModel)
            .where(CddMoleculeImportModel.workspace_id == workspace_id)
            .order_by(CddMoleculeImportModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain_tracked(m) for m in models]

    # ------------------------------------------------------------------
    # Mapping: SA model -> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: CddMoleculeImportModel) -> CddMoleculeImport:
        return CddMoleculeImport(
            id=model.id,
            workspace_id=model.workspace_id,
            cdd_vault_id=model.cdd_vault_id,
            import_mode=CddImportMode(model.import_mode),
            originating_org_id=model.originating_org_id,
            filter_criteria=model.filter_criteria,
            status=CddMoleculeImportStatus(model.status),
            workflow_id=model.workflow_id,
            total_count=model.total_count,
            registered_count=model.registered_count,
            duplicate_count=model.duplicate_count,
            error_count=model.error_count,
            skipped_count=model.skipped_count,
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

    def _to_model(self, aggregate: CddMoleculeImport) -> CddMoleculeImportModel:
        return CddMoleculeImportModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            cdd_vault_id=aggregate.cdd_vault_id,
            import_mode=aggregate.import_mode.value,
            originating_org_id=aggregate.originating_org_id,
            filter_criteria=aggregate.filter_criteria,
            status=aggregate.status.value,
            workflow_id=aggregate.workflow_id,
            total_count=aggregate.total_count,
            registered_count=aggregate.registered_count,
            duplicate_count=aggregate.duplicate_count,
            error_count=aggregate.error_count,
            skipped_count=aggregate.skipped_count,
            last_processed_offset=aggregate.last_processed_offset,
            submitted_by=aggregate.submitted_by,
            submitted_at=aggregate.submitted_at,
            completed_at=aggregate.completed_at,
            version=aggregate.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (UPDATE)
    # ------------------------------------------------------------------

    def _update_model(self, model: CddMoleculeImportModel, aggregate: CddMoleculeImport) -> None:
        model.status = aggregate.status.value
        model.workflow_id = aggregate.workflow_id
        model.total_count = aggregate.total_count
        model.registered_count = aggregate.registered_count
        model.duplicate_count = aggregate.duplicate_count
        model.error_count = aggregate.error_count
        model.skipped_count = aggregate.skipped_count
        model.last_processed_offset = aggregate.last_processed_offset
        model.completed_at = aggregate.completed_at
