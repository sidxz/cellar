"""SQLAlchemy model for BulkRegistration aggregate."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Index, Integer, String, Uuid
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
    submitted_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
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
    completed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_bulk_reg_ws_status", "workspace_id", "status"),
    )
