"""SQLAlchemy models for the RGroupDecompositionRun aggregate + its assignment
rows. Columns match migration 057_rgroup_decomposition_runs exactly."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    VersionMixin,
    WorkspaceIdMixin,
)


class RGroupDecompositionRunModel(Base, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "rgroup_decomposition_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    membership_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    core_smiles: Mapped[str] = mapped_column(Text, nullable=False)
    core_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rgroup_labels: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class RGroupAssignmentModel(Base):
    __tablename__ = "rgroup_assignments"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rgroup_decomposition_runs.id", ondelete="CASCADE"), primary_key=True
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    rgroups: Mapped[dict] = mapped_column(JSONB, nullable=False)
