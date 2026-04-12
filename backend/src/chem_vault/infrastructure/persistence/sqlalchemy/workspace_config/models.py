"""SQLAlchemy models for workspace configuration context."""

from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    custom_field_definitions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    default_molecule_type: Mapped[str | None] = mapped_column(String(50))
    # TODO: migrate audit_reason_policy and formulation_number_scheme from JSON to Text —
    # these are str|None semantically, but were originally created as JSON columns.
    # The JSON type works correctly for string values. A future migration should
    # ALTER COLUMN ... TYPE TEXT USING ...::text to match the Python annotation.
    audit_reason_policy: Mapped[str | None] = mapped_column(JSON, nullable=True)
    signature_required_for: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    audit_retention_days: Mapped[int | None] = mapped_column()
    formulation_number_scheme: Mapped[str | None] = mapped_column(JSON, nullable=True)
    external_vault_id: Mapped[str | None] = mapped_column("cdd_vault_id", String(50))


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


class CustomFieldDefinitionModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """CustomFieldDefinition — workspace-scoped custom field schema."""

    __tablename__ = "custom_field_definitions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    applies_to: Mapped[str] = mapped_column(String(20), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pick_list_values: Mapped[list | None] = mapped_column(JSON, nullable=True)
    vocabulary_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controlled_vocabularies.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", "applies_to", name="uq_cfd_ws_name_target"),
    )


class SaltEntryModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """SaltEntry — workspace-scoped salt catalog entry for chemical registration."""

    __tablename__ = "salt_catalog"

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    smiles: Mapped[str] = mapped_column(String(500), nullable=False)
    molecular_weight: Mapped[float] = mapped_column(Float, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "code", name="uq_salt_ws_code"),
    )


class RegistrationFormModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """RegistrationForm — workspace-scoped form template for molecule/batch registration."""

    __tablename__ = "registration_forms"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    applies_to: Mapped[str] = mapped_column(String(20), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    field_overrides: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", "applies_to", name="uq_regform_ws_name_target"),
    )


class ExternalApiKeyModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """ExternalApiKey — workspace-scoped external API key metadata."""

    __tablename__ = "external_api_keys"

    key_name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    key_prefix: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_api_key_ws_name", "workspace_id", "key_name", unique=True),
    )


class OntologySlotDefinitionModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """OntologySlotDefinition — workspace-scoped ontology annotation slot."""

    __tablename__ = "ontology_slot_definitions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    ontology_sources: Mapped[list] = mapped_column(JSONB, nullable=False)
    root_concept_id: Mapped[str | None] = mapped_column(String(500))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    allow_free_text: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index("ix_ontology_slot_ws_name", "workspace_id", "name", unique=True),
    )


class ProtocolFormModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """ProtocolForm — workspace-scoped template for protocol creation."""

    __tablename__ = "protocol_forms"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    protocol_type: Mapped[str | None] = mapped_column(String(30))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    readout_templates: Mapped[list] = mapped_column(JSONB, nullable=False)
    condition_templates: Mapped[list | None] = mapped_column(JSONB)
    ontology_defaults: Mapped[list | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_protocol_form_ws", "workspace_id"),
    )
