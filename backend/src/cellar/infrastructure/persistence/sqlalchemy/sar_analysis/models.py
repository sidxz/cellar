"""SQLAlchemy model for ScaffoldTreeJob aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    VersionMixin,
    WorkspaceIdMixin,
)


class ScaffoldTreeJobModel(Base, WorkspaceIdMixin, VersionMixin):
    """Persistent state for a ScaffoldTreeJob aggregate.

    Columns match migration 038_scaffold_tree_jobs exactly.
    """

    __tablename__ = "scaffold_tree_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ids_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
