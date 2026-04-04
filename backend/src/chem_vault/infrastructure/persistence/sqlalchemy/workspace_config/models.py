"""SQLAlchemy models for workspace configuration context."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class OrganizationModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Organization — provenance entity for companies, partners, CROs, vendors."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_type: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_org_ws_name"),
    )


class WorkspaceSettingsModel(Base, EntityModelMixin, VersionMixin):
    """WorkspaceSettings — singleton domain configuration per workspace.

    The ``id`` column IS the workspace_id (1:1 relationship).
    No WorkspaceIdMixin needed — the id itself is the workspace identity.
    """

    __tablename__ = "workspace_settings"

    registration_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    custom_field_definitions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    default_molecule_type: Mapped[str | None] = mapped_column(String(50))
    audit_reason_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    signature_required_for: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    audit_retention_days: Mapped[int | None] = mapped_column()
    formulation_number_scheme: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )


class ControlledVocabularyModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """ControlledVocabulary — workspace-level standardized picklists."""

    __tablename__ = "controlled_vocabularies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_vocab_ws_name"),
    )
