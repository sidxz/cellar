"""SQLAlchemy models for Shipment aggregate."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class ShipmentModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Persistent model for Shipment aggregate root."""

    __tablename__ = "shipments"

    destination_org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, server_default="outbound")
    # SET NULL by design — a deleted loan detaches its shipments (migration 071)
    loan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("plate_loans.id", ondelete="SET NULL")
    )
    tracking_number: Mapped[str | None] = mapped_column(String(255))
    carrier: Mapped[str | None] = mapped_column(String(100))
    shipping_date: Mapped[date | None] = mapped_column(Date)
    expected_arrival_date: Mapped[date | None] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    shipping_conditions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[ShipmentItemModel]] = relationship(
        "ShipmentItemModel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (Index("ix_shipments_loan", "loan_id"),)


class ShipmentItemModel(Base, EntityModelMixin):
    """Persistent model for ShipmentItem owned entity."""

    __tablename__ = "shipment_items"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="sample")
    # Polymorphic loose reference (plate or sample) — no FK, like plate_comments.target_id.
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount_shipped_value: Mapped[float | None] = mapped_column(Float)
    amount_shipped_unit: Mapped[str | None] = mapped_column(String(30))

    __table_args__ = (Index("ix_shipment_items_item", "item_type", "item_id"),)
