"""SQLAlchemy models for research organization context."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
