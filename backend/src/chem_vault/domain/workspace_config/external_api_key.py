"""ExternalApiKey aggregate — domain model for workspace-scoped API key metadata."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.events import (
    ExternalApiKeyCreated,
    ExternalApiKeyUpdated,
)

__all__ = ["ExternalApiKey", "ExternalApiKeyCreated", "ExternalApiKeyUpdated"]

# Sentinel for "not provided" in update()
UNSET = object()


class ExternalApiKey(AggregateRoot):
    """Aggregate root for workspace-scoped external API key metadata.

    Stores *metadata only* (key name, label, masked prefix, active flag).
    The actual secret value is stored externally via a SecretProvider.

    key_name is unique per workspace (e.g. "bioportal", "cdd_vault").
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        key_name: str,
        label: str,
        description: str | None = None,
        key_prefix: str,
        is_active: bool = True,
        created_by: uuid.UUID,
        last_used_at: datetime | None = None,
        version: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(
            id=id,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
        )
        self.workspace_id = workspace_id
        self.key_name = key_name
        self.label = label
        self.description = description
        self.key_prefix = key_prefix
        self.is_active = is_active
        self.created_by = created_by
        self.last_used_at = last_used_at

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        key_name: str,
        label: str,
        description: str | None = None,
        key_prefix: str,
        created_by: uuid.UUID,
    ) -> ExternalApiKey:
        """Create and validate a new ExternalApiKey metadata record."""
        if not key_name or not key_name.strip():
            raise ValidationError("key_name must not be empty")
        if not label or not label.strip():
            raise ValidationError("label must not be empty")
        if not key_prefix or not key_prefix.strip():
            raise ValidationError("key_prefix must not be empty")

        entry = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            key_name=key_name.strip(),
            label=label.strip(),
            description=description.strip() if description else None,
            key_prefix=key_prefix.strip(),
            created_by=created_by,
        )
        entry.register_event(
            ExternalApiKeyCreated(
                aggregate_id=entry.id,
                aggregate_type="ExternalApiKey",
                workspace_id=workspace_id,
                key_name=key_name.strip(),
            )
        )
        return entry

    # ------------------------------------------------------------------
    # Mutation commands
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        label: str | object = UNSET,
        description: str | None | object = UNSET,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if label is not UNSET:
            label_str = str(label).strip()
            if not label_str:
                raise ValidationError("label must not be empty")
            self.label = label_str
        if description is not UNSET:
            if description is None:
                self.description = None
            else:
                self.description = str(description).strip() or None

        self.updated_at = datetime.now(UTC)
        self.register_event(
            ExternalApiKeyUpdated(
                aggregate_id=self.id,
                aggregate_type="ExternalApiKey",
                workspace_id=self.workspace_id,
            )
        )

    def update_prefix(self, new_prefix: str) -> None:
        """Update the masked display prefix after a key rotation."""
        if not new_prefix or not new_prefix.strip():
            raise ValidationError("key_prefix must not be empty")
        self.key_prefix = new_prefix.strip()
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ExternalApiKeyUpdated(
                aggregate_id=self.id,
                aggregate_type="ExternalApiKey",
                workspace_id=self.workspace_id,
            )
        )

    def deactivate(self) -> None:
        """Mark this API key as inactive (soft-disable)."""
        self.is_active = False
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ExternalApiKeyUpdated(
                aggregate_id=self.id,
                aggregate_type="ExternalApiKey",
                workspace_id=self.workspace_id,
            )
        )

    def activate(self) -> None:
        """Re-enable a previously deactivated API key."""
        self.is_active = True
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ExternalApiKeyUpdated(
                aggregate_id=self.id,
                aggregate_type="ExternalApiKey",
                workspace_id=self.workspace_id,
            )
        )

    def mark_used(self) -> None:
        """Record the last-used timestamp (no domain event — high-frequency)."""
        self.last_used_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
