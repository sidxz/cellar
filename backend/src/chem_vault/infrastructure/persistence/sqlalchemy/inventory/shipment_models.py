"""SQLAlchemy models for Shipment aggregate."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
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


class ShipmentItemModel(Base, EntityModelMixin):
    """Persistent model for ShipmentItem owned entity."""

    __tablename__ = "shipment_items"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount_shipped_value: Mapped[float] = mapped_column(Float, nullable=False)
    amount_shipped_unit: Mapped[str] = mapped_column(String(30), nullable=False)
