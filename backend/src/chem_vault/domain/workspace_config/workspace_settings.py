"""WorkspaceSettings aggregate — domain configuration per workspace.

Identity: id == workspace_id (singleton per workspace).
Sentinel owns workspace identity; Chem-Vault stores domain-specific config only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.workspace_config.events import WorkspaceSettingsUpdated

_SENTINEL = object()


class WorkspaceSettings(AggregateRoot):
    """Workspace-level domain configuration.

    The ``id`` field IS the workspace_id — there is exactly one WorkspaceSettings
    per workspace.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        registration_rules: dict | None = None,
        custom_field_definitions: dict | None = None,
        default_molecule_type: str | None = None,
        audit_reason_policy: dict | None = None,
        signature_required_for: list[str] | None = None,
        audit_retention_days: int | None = None,
        formulation_number_scheme: dict | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.registration_rules = registration_rules or {}
        self.custom_field_definitions = custom_field_definitions or {}
        self.default_molecule_type = default_molecule_type
        self.audit_reason_policy = audit_reason_policy or {}
        self.signature_required_for = signature_required_for or []
        self.audit_retention_days = audit_retention_days
        self.formulation_number_scheme = formulation_number_scheme or {}

    @property
    def workspace_id(self) -> uuid.UUID:
        """Alias — the id IS the workspace_id."""
        return self.id

    @classmethod
    def create_default(cls, *, workspace_id: uuid.UUID) -> WorkspaceSettings:
        """Factory for a new workspace with all default settings."""
        return cls(id=workspace_id)

    def update(
        self,
        *,
        registration_rules: dict | object = _SENTINEL,
        custom_field_definitions: dict | object = _SENTINEL,
        default_molecule_type: str | None | object = _SENTINEL,
        audit_reason_policy: dict | object = _SENTINEL,
        signature_required_for: list[str] | object = _SENTINEL,
        audit_retention_days: int | None | object = _SENTINEL,
        formulation_number_scheme: dict | object = _SENTINEL,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if registration_rules is not _SENTINEL:
            self.registration_rules = registration_rules  # type: ignore[assignment]
        if custom_field_definitions is not _SENTINEL:
            self.custom_field_definitions = custom_field_definitions  # type: ignore[assignment]
        if default_molecule_type is not _SENTINEL:
            self.default_molecule_type = default_molecule_type  # type: ignore[assignment]
        if audit_reason_policy is not _SENTINEL:
            self.audit_reason_policy = audit_reason_policy  # type: ignore[assignment]
        if signature_required_for is not _SENTINEL:
            self.signature_required_for = signature_required_for  # type: ignore[assignment]
        if audit_retention_days is not _SENTINEL:
            self.audit_retention_days = audit_retention_days  # type: ignore[assignment]
        if formulation_number_scheme is not _SENTINEL:
            self.formulation_number_scheme = formulation_number_scheme  # type: ignore[assignment]
        self.updated_at = datetime.now(UTC)
        self.register_event(
            WorkspaceSettingsUpdated(
                aggregate_id=self.id,
                aggregate_type="WorkspaceSettings",
            )
        )
