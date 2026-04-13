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
from sqlalchemy.dialects.postgresql import JSON, JSONB
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
    salt_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("salt_catalog.id", ondelete="SET NULL"), nullable=True
    )
    salt_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salt_smiles: Mapped[str | None] = mapped_column(String(500), nullable=True)
    salt_stoichiometry: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    formula_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
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


class RegisteredPlateModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Standalone physical plate in inventory."""

    __tablename__ = "registered_plates"

    barcode: Mapped[str] = mapped_column(String(100), nullable=False)
    plate_label: Mapped[str] = mapped_column(String(300), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    plate_type: Mapped[str] = mapped_column(String(30), nullable=False)
    well_map: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="registered"
    )
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("storage_locations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    parent_plate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("registered_plates.id")
    )
    registered_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("workspace_id", "barcode", name="uq_reg_plate_ws_barcode"),
        Index("ix_reg_plate_status", "workspace_id", "status"),
        Index("ix_reg_plate_type", "workspace_id", "plate_type"),
        Index("ix_reg_plate_location", "storage_location_id"),
        Index("ix_reg_plate_project", "project_id"),
        Index("ix_reg_plate_parent", "parent_plate_id"),
    )


class ImportTemplateModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Saved column mapping for plate data imports."""

    __tablename__ = "import_templates"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    column_mappings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    default_protocol_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index("ix_import_template_ws", "workspace_id"),
    )
