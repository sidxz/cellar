"""SQLAlchemy repository for BulkDisclosure aggregates."""

from __future__ import annotations

from chem_vault.domain.chemical_registration.bulk_disclosure import BulkDisclosure
from chem_vault.domain.chemical_registration.enums import BulkDisclosureStatus
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_models import (
    BulkDisclosureModel,
)


class SQLAlchemyBulkDisclosureRepository(
    SQLAlchemyRepository[BulkDisclosure, BulkDisclosureModel]
):
    model_class = BulkDisclosureModel

    # ------------------------------------------------------------------
    # Mapping: SA model -> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: BulkDisclosureModel) -> BulkDisclosure:
        return BulkDisclosure(
            id=model.id,
            workspace_id=model.workspace_id,
            source_file=model.source_file,
            partner_org_id=model.partner_org_id,
            submitted_by=model.submitted_by,
            submitted_at=model.submitted_at,
            status=BulkDisclosureStatus(model.status),
            total_count=model.total_count,
            disclosed_count=model.disclosed_count,
            merged_count=model.merged_count,
            conflict_count=model.conflict_count,
            error_count=model.error_count,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (INSERT)
    # ------------------------------------------------------------------

    def _to_model(self, aggregate: BulkDisclosure) -> BulkDisclosureModel:
        return BulkDisclosureModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            source_file=aggregate.source_file,
            partner_org_id=aggregate.partner_org_id,
            submitted_by=aggregate.submitted_by,
            submitted_at=aggregate.submitted_at,
            status=aggregate.status.value,
            total_count=aggregate.total_count,
            disclosed_count=aggregate.disclosed_count,
            merged_count=aggregate.merged_count,
            conflict_count=aggregate.conflict_count,
            error_count=aggregate.error_count,
            completed_at=aggregate.completed_at,
            version=aggregate.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (UPDATE)
    # ------------------------------------------------------------------

    def _update_model(
        self, model: BulkDisclosureModel, aggregate: BulkDisclosure
    ) -> None:
        model.status = aggregate.status.value
        model.total_count = aggregate.total_count
        model.disclosed_count = aggregate.disclosed_count
        model.merged_count = aggregate.merged_count
        model.conflict_count = aggregate.conflict_count
        model.error_count = aggregate.error_count
        model.completed_at = aggregate.completed_at
