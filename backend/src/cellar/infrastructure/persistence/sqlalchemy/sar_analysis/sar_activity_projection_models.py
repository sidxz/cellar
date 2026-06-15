"""SQLAlchemy models for the SarActivityProjection aggregate + its sparse value
rows. Columns match migration 058_sar_activity_projections exactly."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    VersionMixin,
    WorkspaceIdMixin,
)


class SarActivityProjectionModel(Base, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "sar_activity_projections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    membership_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class SarActivityValueModel(Base):
    __tablename__ = "sar_activity_values"

    projection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sar_activity_projections.id", ondelete="CASCADE"), primary_key=True
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scalar: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
