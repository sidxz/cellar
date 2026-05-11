"""SQLAlchemy models for research organization context."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)

# Import models referenced by ForeignKeys so they are registered in
# Base.metadata before the mapper resolves cross-context FK targets.
import chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models  # noqa: F401,E402
import chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models  # noqa: F401,E402


# ---------------------------------------------------------------------------
# Association tables
# ---------------------------------------------------------------------------

molecule_projects = Table(
    "molecule_projects",
    Base.metadata,
    Column(
        "molecule_id",
        Uuid(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "project_id",
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ProjectModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Project — workspace-level research project."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_project_ws_name"),
    )


class CollectionModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Collection — curated set of molecules."""

    __tablename__ = "collections"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL")
    )
    owned_by_org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, server_default="private")
    is_frozen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    derived_from_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_collection_ws_name"),
    )


class CollectionMoleculeModel(Base):
    """Join table — collection membership (no entity mixins, pure join)."""

    __tablename__ = "collection_molecules"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("molecules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_collection_molecules_molecule_id", "molecule_id"),
    )


class SavedSearchModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """SavedSearch — persisted search criteria for re-execution."""

    __tablename__ = "saved_searches"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL")
    )
    query: Mapped[dict] = mapped_column(JSONB, nullable=False)
    columns: Mapped[dict | None] = mapped_column(JSONB)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="private")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_count: Mapped[int | None] = mapped_column()

    __table_args__ = (
        Index("ix_saved_searches_ws_creator", "workspace_id", "created_by"),
    )


class ProjectMemberModel(Base):
    """Project membership — who can access a project and at what role."""

    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_project_members_user", "user_id"),
    )


# -----------------------------------------------------------------------------
# Screen Campaign aggregate (Task 3.1)
# -----------------------------------------------------------------------------


class CampaignModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Campaign — aggregate root for a screening campaign."""

    __tablename__ = "campaign"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="draft"
    )
    compound_source: Mapped[dict] = mapped_column(JSONB, nullable=False)
    publishes_collection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    source_protocols: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    signature_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    supersedes_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    superseded_by_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    published_collection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )

    channels: Mapped[list[CampaignChannelModel]] = relationship(
        "CampaignChannelModel",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CampaignChannelModel.display_order",
    )
    results: Mapped[list[CampaignResultModel]] = relationship(
        "CampaignResultModel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_campaign_workspace_project", "workspace_id", "project_id"),
        Index("ix_campaign_supersedes", "supersedes_campaign_id"),
    )


class CampaignChannelModel(Base, EntityModelMixin):
    """CampaignChannel — owned child of Campaign (one per protocol/readout)."""

    __tablename__ = "campaign_channel"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    readout_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    selection_rule: Mapped[str] = mapped_column(String(32), nullable=False)
    qualifier_handling: Mapped[str] = mapped_column(String(32), nullable=False)
    qc_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hit_threshold: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CampaignResultModel(Base, EntityModelMixin):
    """CampaignResult — owned child of Campaign (one per molecule)."""

    __tablename__ = "campaign_result"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    representative_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    decision: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="deferred"
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    measurements: Mapped[list[CampaignMeasurementModel]] = relationship(
        "CampaignMeasurementModel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "uq_campaign_result_molecule",
            "campaign_id",
            "molecule_id",
            unique=True,
        ),
    )


class CampaignMeasurementModel(Base, EntityModelMixin):
    """CampaignMeasurement — owned grandchild (one per result x channel)."""

    __tablename__ = "campaign_measurement"

    result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign_result.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign_channel.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_qualifier: Mapped[str] = mapped_column(String(16), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    hit_call: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    source_curve_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    source_readout_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    protocol_name_snapshot: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    protocol_version_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    run_date_snapshot: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index(
            "uq_campaign_measurement_result_channel",
            "result_id",
            "channel_id",
            unique=True,
        ),
        Index("ix_campaign_measurement_source_run", "source_run_id"),
    )
