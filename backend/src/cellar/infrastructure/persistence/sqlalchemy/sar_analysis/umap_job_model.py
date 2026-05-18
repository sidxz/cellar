"""UmapJobModel — SQLAlchemy table mapping for umap_jobs.

Columns match migration 039_umap_jobs exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import Base


class UmapJobModel(Base):
    """Persistent state for a UmapJob aggregate."""

    __tablename__ = "umap_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    ids_hash: Mapped[str] = mapped_column(Text, nullable=False)
    picker: Mapped[str] = mapped_column(String(20), nullable=False)
    picker_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    picker_param_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint(
            "picker IN ('maxmin', 'butina')",
            name="umap_jobs_picker_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'ready', 'failed', 'cancelled')",
            name="umap_jobs_status_check",
        ),
    )
