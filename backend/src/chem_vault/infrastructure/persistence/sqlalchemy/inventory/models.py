"""SQLAlchemy models for inventory context — batches, samples, storage locations."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class BatchModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Physical preparation of a molecule."""

    __tablename__ = "batches"

    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    batch_number: Mapped[str] = mapped_column(String(50), nullable=False)
    salt_form: Mapped[str | None] = mapped_column(String(100))
    purity: Mapped[float | None] = mapped_column(Float)
    amount_value: Mapped[float] = mapped_column(Float, nullable=False)
    amount_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    concentration_value: Mapped[float | None] = mapped_column(Float)
    concentration_unit: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    supplier_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    vendor_catalog_number: Mapped[str | None] = mapped_column(String(200))
    vendor_lot_number: Mapped[str | None] = mapped_column(String(200))
    chemist: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    synthesis_date: Mapped[str | None] = mapped_column(Date)
    expiry_date: Mapped[str | None] = mapped_column(Date)
    notebook_reference: Mapped[str | None] = mapped_column(String(200))
    storage_temperature_celsius: Mapped[float | None] = mapped_column(Float)
    storage_humidity_percent: Mapped[float | None] = mapped_column(Float)
    storage_light_condition: Mapped[str | None] = mapped_column(String(30))
    storage_conditions_notes: Mapped[str | None] = mapped_column(Text)
    appearance: Mapped[str | None] = mapped_column(String(500))
    custom_fields: Mapped[dict | None] = mapped_column(JSON)
    synthesis_route_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    synthesis_step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    synthesis_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    __table_args__ = (
        UniqueConstraint("workspace_id", "batch_number", name="uq_batch_ws_number"),
        Index("ix_batch_molecule", "molecule_id"),
    )


class SampleModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Discrete physical container of material from a batch."""

    __tablename__ = "samples"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("batches.id"), nullable=False, index=True
    )
    barcode: Mapped[str] = mapped_column(String(100), nullable=False)
    container_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_value: Mapped[float] = mapped_column(Float, nullable=False)
    amount_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    concentration_value: Mapped[float | None] = mapped_column(Float)
    concentration_unit: Mapped[str | None] = mapped_column(String(20))
    solvent: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="available"
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("storage_locations.id")
    )
    freeze_thaw_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    low_stock_threshold: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("workspace_id", "barcode", name="uq_sample_ws_barcode"),
        Index("ix_sample_batch", "batch_id"),
        Index("ix_sample_location", "location_id"),
        Index("ix_sample_status", "workspace_id", "status"),
    )


class StorageLocationModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Physical storage hierarchy (site -> building -> room -> freezer -> shelf -> box)."""

    __tablename__ = "storage_locations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("storage_locations.id")
    )
    parent_type: Mapped[str | None] = mapped_column(String(30))
    barcode: Mapped[str | None] = mapped_column(String(100))
    temperature: Mapped[str | None] = mapped_column(String(50))
    rows: Mapped[int | None] = mapped_column(Integer)
    columns: Mapped[int | None] = mapped_column(Integer)
    capacity: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_storage_ws_type", "workspace_id", "type"),
        Index("ix_storage_parent", "parent_id"),
    )
