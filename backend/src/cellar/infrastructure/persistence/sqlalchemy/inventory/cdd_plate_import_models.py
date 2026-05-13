"""SQLAlchemy models for CDD plate import tracking."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class CddPlateImportModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """CDD vault plate import operation."""

    __tablename__ = "cdd_plate_imports"

    cdd_vault_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="pending")
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    plates_registered: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    plates_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    plates_error: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    wells_mapped: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    wells_unresolved: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_processed_offset: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    submitted_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_cdd_plate_import_ws_status", "workspace_id", "status"),)


class CddPlateSyncModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Maps CDD plate IDs to internal RegisteredPlate IDs."""

    __tablename__ = "cdd_plate_sync"

    cdd_vault_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cdd_plate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    plate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index(
            "uq_cdd_plate_sync_ws_vault_plate",
            "workspace_id",
            "cdd_vault_id",
            "cdd_plate_id",
            unique=True,
        ),
    )
