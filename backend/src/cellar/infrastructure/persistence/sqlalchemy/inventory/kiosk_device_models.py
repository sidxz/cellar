"""SQLAlchemy model for the KioskDevice aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class KioskDeviceModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Persistent model for KioskDevice — token stored as sha256 hexdigest only."""

    __tablename__ = "kiosk_devices"

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_kiosk_devices_ws_name"),
        # Token lookup is cross-workspace (the token is the identity) — unique
        # doubles as the lookup index.
        UniqueConstraint("token_hash", name="uq_kiosk_devices_token_hash"),
        Index("ix_kiosk_devices_ws_org", "workspace_id", "org_id"),
    )
