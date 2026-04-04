"""SQLAlchemy repository for WorkspaceSettings aggregates."""

from __future__ import annotations

from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    WorkspaceSettingsModel,
)


class SQLAlchemyWorkspaceSettingsRepository(
    SQLAlchemyRepository[WorkspaceSettings, WorkspaceSettingsModel]
):
    model_class = WorkspaceSettingsModel

    def _to_domain(self, model: WorkspaceSettingsModel) -> WorkspaceSettings:
        return WorkspaceSettings(
            id=model.id,
            registration_rules=model.registration_rules,
            custom_field_definitions=model.custom_field_definitions,
            default_molecule_type=model.default_molecule_type,
            audit_reason_policy=model.audit_reason_policy,
            signature_required_for=list(model.signature_required_for or []),
            audit_retention_days=model.audit_retention_days,
            formulation_number_scheme=model.formulation_number_scheme,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: WorkspaceSettings) -> WorkspaceSettingsModel:
        return WorkspaceSettingsModel(
            id=aggregate.id,
            registration_rules=aggregate.registration_rules,
            custom_field_definitions=aggregate.custom_field_definitions,
            default_molecule_type=aggregate.default_molecule_type,
            audit_reason_policy=aggregate.audit_reason_policy,
            signature_required_for=aggregate.signature_required_for,
            audit_retention_days=aggregate.audit_retention_days,
            formulation_number_scheme=aggregate.formulation_number_scheme,
            version=aggregate.version,
        )

    def _update_model(
        self, model: WorkspaceSettingsModel, aggregate: WorkspaceSettings
    ) -> None:
        model.registration_rules = aggregate.registration_rules
        model.custom_field_definitions = aggregate.custom_field_definitions
        model.default_molecule_type = aggregate.default_molecule_type
        model.audit_reason_policy = aggregate.audit_reason_policy
        model.signature_required_for = aggregate.signature_required_for
        model.audit_retention_days = aggregate.audit_retention_days
        model.formulation_number_scheme = aggregate.formulation_number_scheme
