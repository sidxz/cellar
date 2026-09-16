"""SQLAlchemy models for PlateLoan aggregate."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class PlateLoanModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Persistent model for PlateLoan aggregate root."""

    __tablename__ = "plate_loans"

    owner_org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    borrower_org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    due_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[LoanItemModel]] = relationship(
        "LoanItemModel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_plate_loans_ws_status", "workspace_id", "status"),
        Index("ix_plate_loans_owner_org", "owner_org_id"),
        Index("ix_plate_loans_borrower_org", "borrower_org_id"),
    )


class LoanItemModel(Base, EntityModelMixin):
    """Persistent model for LoanItem owned entity (no version column)."""

    __tablename__ = "plate_loan_items"

    loan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("plate_loans.id", ondelete="CASCADE"), nullable=False
    )
    # No FK to registered_plates — deliberate loose reference (migration 063):
    # loan history must survive plate deletion.
    plate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # uq_loan_items_active_plate is NOT declared here — it's a raw-SQL
    # partial unique index (see migration 063) that ORM constructs can't
    # express; the migration owns it.
    __table_args__ = (
        Index("ix_loan_items_loan", "loan_id"),
        Index("ix_loan_items_plate", "plate_id"),
    )
