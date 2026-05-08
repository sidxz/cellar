"""SQLAlchemy repository for WorkspaceSettings aggregates."""

from __future__ import annotations

import uuid

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

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> WorkspaceSettings | None:
        """WorkspaceSettings uses id == workspace_id (singleton per workspace)."""
        return await self.find_by_workspace_id(workspace_id)

    async def find_by_workspace_id(
        self, workspace_id: uuid.UUID
    ) -> WorkspaceSettings | None:
        """Load the singleton settings row for a workspace.

        WorkspaceSettings has ``id == workspace_id`` by design — there is at
        most one row per workspace. This is the only repository that may load
        without a separate workspace filter.
        """
        return await self._find_by_id_unscoped(workspace_id)

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
            cdd_vault_id=model.cdd_vault_id,
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
            cdd_vault_id=aggregate.cdd_vault_id,
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
        model.cdd_vault_id = aggregate.cdd_vault_id
