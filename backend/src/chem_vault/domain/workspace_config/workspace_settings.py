"""WorkspaceSettings aggregate — domain configuration per workspace.

Identity: id == workspace_id (singleton per workspace).
Sentinel owns workspace identity; Chem-Vault stores domain-specific config only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.workspace_config.events import WorkspaceSettingsUpdated


class WorkspaceSettings(AggregateRoot):
    """Workspace-level domain configuration.

    The ``id`` field IS the workspace_id — there is exactly one WorkspaceSettings
    per workspace.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        registration_rules: dict[str, Any] | None = None,
        custom_field_definitions: list[dict[str, Any]] | None = None,
        default_molecule_type: str | None = None,
        audit_reason_policy: str | None = None,
        signature_required_for: list[str] | None = None,
        audit_retention_days: int | None = None,
        formulation_number_scheme: str | None = None,
        cdd_vault_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.registration_rules = registration_rules or {}
        self.custom_field_definitions = custom_field_definitions if isinstance(custom_field_definitions, list) else []
        self.default_molecule_type = default_molecule_type
        self.audit_reason_policy = audit_reason_policy if isinstance(audit_reason_policy, str) else None
        self.signature_required_for = signature_required_for or []
        self.audit_retention_days = audit_retention_days
        self.formulation_number_scheme = formulation_number_scheme if isinstance(formulation_number_scheme, str) else None
        self.cdd_vault_id = cdd_vault_id

    @property
    def workspace_id(self) -> uuid.UUID:
        """Alias — the id IS the workspace_id."""
        return self.id

    @classmethod
    def create_default(cls, *, workspace_id: uuid.UUID) -> WorkspaceSettings:
        """Factory for a new workspace with all default settings."""
        return cls(id=workspace_id)

    def update(self, **fields: object) -> None:
        """Partial update — only keys present in ``fields`` are changed.

        Accepted keys: registration_rules, custom_field_definitions,
        default_molecule_type, audit_reason_policy, signature_required_for,
        audit_retention_days, formulation_number_scheme.
        """
        for key in (
            "registration_rules", "custom_field_definitions", "default_molecule_type",
            "audit_reason_policy", "signature_required_for", "audit_retention_days",
            "formulation_number_scheme", "cdd_vault_id",
        ):
            if key in fields:
                setattr(self, key, fields[key])
        self.updated_at = datetime.now(UTC)
        self.register_event(
            WorkspaceSettingsUpdated(
                aggregate_id=self.id,
                aggregate_type="WorkspaceSettings",
                workspace_id=self.workspace_id,
            )
        )
