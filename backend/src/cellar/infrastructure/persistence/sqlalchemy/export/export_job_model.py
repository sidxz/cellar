"""SQLAlchemy model for ExportJob aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    VersionMixin,
    WorkspaceIdMixin,
)


class ExportJobModel(Base, WorkspaceIdMixin, VersionMixin):
    """Persistent state for an ExportJob aggregate.

    Columns match migration 036_export_jobs exactly.  No created_at/updated_at
    — the aggregate tracks timing via requested_at/started_at/completed_at.
    """

    __tablename__ = "export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    query_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
