"""SQLAlchemy model for SynthesisRequest aggregate."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, Date, Float, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class SynthesisRequestModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Persistent model for SynthesisRequest aggregate."""

    __tablename__ = "synthesis_requests"

    __table_args__ = (
        Index("ix_synthesis_requests_workspace_status", "workspace_id", "status"),
        Index("ix_synthesis_requests_molecule", "workspace_id", "molecule_id"),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    # Target structure (flattened ChemicalStructure VO)
    target_smiles: Mapped[str | None] = mapped_column(Text)
    target_inchi: Mapped[str | None] = mapped_column(Text)
    target_inchi_key: Mapped[str | None] = mapped_column(String(27))

    # Requested amount (flattened Amount VO)
    requested_amount_value: Mapped[float] = mapped_column(Float, nullable=False)
    requested_amount_unit: Mapped[str] = mapped_column(String(30), nullable=False)

    target_purity: Mapped[float | None] = mapped_column(Float)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="routine")
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True, default="draft")

    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    parent_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    bulk_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    # Assignment (flattened SynthesisAssignment VO)
    assignment_type: Mapped[str | None] = mapped_column(String(30))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    assigned_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    proposed_route_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    feasibility_notes: Mapped[str | None] = mapped_column(Text)
    feasibility_status: Mapped[str | None] = mapped_column(String(30))

    # Estimated cost (flattened Amount VO)
    estimated_cost_value: Mapped[float | None] = mapped_column(Float)
    estimated_cost_unit: Mapped[str | None] = mapped_column(String(30))

    # Actual cost (flattened Amount VO)
    actual_cost_value: Mapped[float | None] = mapped_column(Float)
    actual_cost_unit: Mapped[str | None] = mapped_column(String(30))

    estimated_completion_date: Mapped[date | None] = mapped_column(Date)
    actual_completion_date: Mapped[date | None] = mapped_column(Date)

    fulfilled_batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    failure_reason: Mapped[str | None] = mapped_column(Text)
