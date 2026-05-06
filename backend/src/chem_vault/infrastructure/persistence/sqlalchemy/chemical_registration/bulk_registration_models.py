"""SQLAlchemy models for BulkRegistration aggregate and its child items."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class BulkRegistrationModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Bulk registration operation — groups multiple molecule registrations from a file upload."""

    __tablename__ = "bulk_registrations"

    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    submitted_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="pending"
    )
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_bulk_reg_ws_status", "workspace_id", "status"),
        Index("ix_bulk_reg_workflow_id", "workspace_id", "workflow_id"),
    )


class BulkRegistrationItemModel(Base):
    """Per-row outcome of a bulk registration — append-only child of BulkRegistration."""

    __tablename__ = "bulk_registration_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    bulk_registration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("bulk_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    molecule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    molecule_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    batch_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_bulk_reg_item_reg_action", "bulk_registration_id", "action"),
        Index("ix_bulk_reg_item_reg_row", "bulk_registration_id", "row_index", unique=True),
    )
