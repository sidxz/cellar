"""SQLAlchemy model for SampleRequest aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class SampleRequestModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Persistent model for SampleRequest aggregate."""

    __tablename__ = "sample_requests"

    requester_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    requested_amount_value: Mapped[float] = mapped_column(Float, nullable=False)
    requested_amount_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    fulfilled_sample_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
