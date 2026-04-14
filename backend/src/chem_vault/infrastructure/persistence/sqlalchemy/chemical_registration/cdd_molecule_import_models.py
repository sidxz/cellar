"""SQLAlchemy model for CddMoleculeImport aggregate."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class CddMoleculeImportModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """CDD vault molecule import operation."""

    __tablename__ = "cdd_molecule_imports"

    cdd_vault_id: Mapped[str] = mapped_column(String(50), nullable=False)
    import_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    originating_org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), nullable=False
    )
    filter_criteria: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="pending"
    )
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    registered_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    last_processed_offset: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    submitted_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_cdd_mol_import_ws_status", "workspace_id", "status"),
    )
