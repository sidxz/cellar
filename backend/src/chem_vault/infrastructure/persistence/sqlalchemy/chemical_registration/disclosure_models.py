"""SQLAlchemy models for disclosure and merge entities."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class BulkDisclosureModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Bulk disclosure operation — groups multiple DisclosureRequests from a single file upload."""

    __tablename__ = "bulk_disclosures"

    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    partner_org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    submitted_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="pending"
    )
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    disclosed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    merged_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    conflict_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DisclosureRequestModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Formal request to disclose the structure of an undisclosed molecule."""

    __tablename__ = "disclosure_requests"

    bulk_disclosure_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("bulk_disclosures.id"), nullable=True
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False
    )
    disclosed_smiles: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_smiles: Mapped[str | None] = mapped_column(Text)
    inchi_key: Mapped[str | None] = mapped_column(String(27))
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="pending"
    )
    resolution_type: Mapped[str | None] = mapped_column(String(30))
    resolved_to_molecule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=True
    )
    matched_molecule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=True
    )
    scientist_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    disclosing_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conflict_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_disclosure_requests_molecule_id", "molecule_id"),
        Index("ix_disclosure_requests_bulk_id", "bulk_disclosure_id"),
    )


class MergeEventModel(Base, EntityModelMixin):
    """Record of a molecule merge operation — insert-only, no version column."""

    __tablename__ = "merge_events"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    source_molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False
    )
    target_molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False
    )
    disclosure_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("disclosure_requests.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    merged_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_merge_events_source", "source_molecule_id"),
        Index("ix_merge_events_target", "target_molecule_id"),
    )
