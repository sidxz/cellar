"""Organization aggregate — provenance entity for companies, partners, CROs, vendors."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.enums import OrganizationType
from chem_vault.domain.workspace_config.events import (
    OrganizationCreated,
    OrganizationDeactivated,
    OrganizationUpdated,
)

_SENTINEL = object()


class Organization(AggregateRoot):
    """A company, institution, or lab participating in the compound lifecycle.

    Workspace-scoped provenance entity — referenced by Molecule, Batch, Run, etc.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        org_type: OrganizationType,
        contact_name: str | None = None,
        contact_email: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("Organization name must not be empty")
        self.workspace_id = workspace_id
        self.name = name.strip()
        self.org_type = org_type
        self.contact_name = contact_name
        self.contact_email = contact_email
        self.notes = notes
        self.is_active = is_active

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        org_type: OrganizationType,
        contact_name: str | None = None,
        contact_email: str | None = None,
        notes: str | None = None,
    ) -> Organization:
        org = cls(
            workspace_id=workspace_id,
            name=name,
            org_type=org_type,
            contact_name=contact_name,
            contact_email=contact_email,
            notes=notes,
        )
        org.register_event(
            OrganizationCreated(
                aggregate_id=org.id,
                aggregate_type="Organization",
                workspace_id=workspace_id,
                name=org.name,
                org_type=org_type,
            )
        )
        return org

    def update(
        self,
        *,
        name: str | object = _SENTINEL,
        org_type: OrganizationType | object = _SENTINEL,
        contact_name: str | None | object = _SENTINEL,
        contact_email: str | None | object = _SENTINEL,
        notes: str | None | object = _SENTINEL,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if name is not _SENTINEL:
            if not name or not str(name).strip():
                raise ValidationError("Organization name must not be empty")
            self.name = str(name).strip()
        if org_type is not _SENTINEL:
            self.org_type = org_type  # type: ignore[assignment]
        if contact_name is not _SENTINEL:
            self.contact_name = contact_name  # type: ignore[assignment]
        if contact_email is not _SENTINEL:
            self.contact_email = contact_email  # type: ignore[assignment]
        if notes is not _SENTINEL:
            self.notes = notes  # type: ignore[assignment]
        self.updated_at = datetime.now(UTC)
        self.register_event(
            OrganizationUpdated(
                aggregate_id=self.id,
                aggregate_type="Organization",
                workspace_id=self.workspace_id,
            )
        )

    def deactivate(self) -> None:
        if not self.is_active:
            raise ValidationError("Organization is already inactive")
        self.is_active = False
        self.updated_at = datetime.now(UTC)
        self.register_event(
            OrganizationDeactivated(
                aggregate_id=self.id,
                aggregate_type="Organization",
                workspace_id=self.workspace_id,
            )
        )

    def activate(self) -> None:
        if self.is_active:
            raise ValidationError("Organization is already active")
        self.is_active = True
        self.updated_at = datetime.now(UTC)
