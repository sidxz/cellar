"""SQLAlchemy models for screening & assay context.

10 tables: targets, plate_templates, protocols, readout_definitions,
condition_definitions, runs, plates, wells, readout_data, dose_response_curves.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


# ---------------------------------------------------------------------------
# Association tables
# ---------------------------------------------------------------------------

protocol_projects = Table(
    "protocol_projects",
    Base.metadata,
    Column(
        "protocol_id",
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "project_id",
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ---------------------------------------------------------------------------
# Reference entities (no VersionMixin — not aggregate roots)
# ---------------------------------------------------------------------------


class TargetModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Biological target referenced by screening protocols."""

    __tablename__ = "targets"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    organism: Mapped[str | None] = mapped_column(String(200))
    gene_name: Mapped[str | None] = mapped_column(String(200))
    uniprot_id: Mapped[str | None] = mapped_column(String(20))
    ncbi_gene_id: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    target_class: Mapped[str | None] = mapped_column(String(100))
    sequence: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_target_ws_name", "workspace_id", "name"),
    )


class PlateTemplateModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Reusable plate layout template."""

    __tablename__ = "plate_templates"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    template_map: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index("ix_plate_template_ws", "workspace_id"),
    )


# ---------------------------------------------------------------------------
# Protocol aggregate + owned entities
# ---------------------------------------------------------------------------


class ProtocolModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Versioned experimental protocol template."""

    __tablename__ = "protocols"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    protocol_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("targets.id")
    )
    category: Mapped[str | None] = mapped_column(String(100))
    protocol_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_protocol_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("protocols.id")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Canonical dose unit for this assay. All wells of all runs of this
    # protocol use this unit; IC50 fits are reported in this unit.
    dose_unit: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="uM"
    )
    # Direction of POS control raw signal — drives normalization formula
    # dispatch. "high" matches the built-in formulas (POS = uninhibited
    # reference); "low" supports labs that label the known-inhibitor wells
    # as POSITIVE_CONTROL.
    pos_control_signal: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="high"
    )
    control_layouts: Mapped[dict | None] = mapped_column(JSONB)
    ontology_annotations: Mapped[dict | None] = mapped_column(JSONB)
    recommended_hit_criteria: Mapped[list | None] = mapped_column(JSONB)
    # Lock state — orthogonal to status. Mirrors RunModel lock fields.
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lock_reason: Mapped[str | None] = mapped_column(Text)

    # Owned entity collections
    readout_definitions: Mapped[list[ReadoutDefinitionModel]] = relationship(
        "ReadoutDefinitionModel",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="protocol",
    )
    condition_definitions: Mapped[list[ConditionDefinitionModel]] = relationship(
        "ConditionDefinitionModel",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="protocol",
    )

    __table_args__ = (
        Index("ix_protocol_ws_name", "workspace_id", "name"),
        Index("ix_protocol_parent", "parent_protocol_id"),
        Index("ix_protocol_ws_status", "workspace_id", "status"),
    )


class ReadoutDefinitionModel(Base, EntityModelMixin):
    """Measurement column definition owned by a protocol."""

    __tablename__ = "readout_definitions"

    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    aggregation: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="none"
    )
    precision: Mapped[int | None] = mapped_column(Integer)
    # JSONB array of normalization formula names (CDD parity: one readout def
    # can emit multiple views, e.g. ["percent_inhibition", "z_score"]).
    # Empty array means no normalization.
    normalizations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    is_calculated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    calculation_formula: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    pick_list_values: Mapped[list | None] = mapped_column(JSONB)
    dose_response_config: Mapped[dict | None] = mapped_column(JSONB)

    protocol: Mapped[ProtocolModel] = relationship(
        "ProtocolModel", back_populates="readout_definitions"
    )

    __table_args__ = (
        Index("ix_readout_def_protocol", "protocol_id"),
    )


class ConditionDefinitionModel(Base, EntityModelMixin):
    """Experimental condition variable owned by a protocol."""

    __tablename__ = "condition_definitions"

    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    pick_list_values: Mapped[list | None] = mapped_column(JSONB)

    protocol: Mapped[ProtocolModel] = relationship(
        "ProtocolModel", back_populates="condition_definitions"
    )

    __table_args__ = (
        Index("ix_condition_def_protocol", "protocol_id"),
    )


# ---------------------------------------------------------------------------
# Run aggregate + owned entities (Plate, Well)
# ---------------------------------------------------------------------------


class RunModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """An execution of a protocol — the central screening experiment record."""

    __tablename__ = "runs"

    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id"), nullable=False
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    operator: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    performed_at_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("runs.id")
    )
    run_relationship_type: Mapped[str | None] = mapped_column(String(30))
    plate_format: Mapped[str | None] = mapped_column(String(10))
    plate_template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("plate_templates.id", ondelete="SET NULL")
    )
    conditions: Mapped[dict | None] = mapped_column(JSONB)
    qc_metrics: Mapped[dict | None] = mapped_column(JSONB)
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lock_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    eln_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    # Owned entity collection
    plates: Mapped[list[PlateModel]] = relationship(
        "PlateModel",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="run",
    )

    __table_args__ = (
        Index("ix_run_protocol", "protocol_id"),
        Index("ix_run_ws_status", "workspace_id", "status"),
        Index("ix_run_parent", "parent_run_id"),
    )


class PlateModel(Base, EntityModelMixin):
    """A microplate belonging to a run."""

    __tablename__ = "plates"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    plate_number: Mapped[int] = mapped_column(Integer, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(100))
    format: Mapped[str | None] = mapped_column(String(10))
    plate_map: Mapped[dict | None] = mapped_column(JSONB)
    parent_plate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    run: Mapped[RunModel] = relationship("RunModel", back_populates="plates")
    wells: Mapped[list[WellModel]] = relationship(
        "WellModel",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="plate",
    )

    __table_args__ = (
        Index("ix_plate_run", "run_id"),
    )


class WellModel(Base, EntityModelMixin):
    """A single well on a plate."""

    __tablename__ = "wells"

    plate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("plates.id", ondelete="CASCADE"), nullable=False
    )
    row: Mapped[str] = mapped_column(String(2), nullable=False)
    column: Mapped[int] = mapped_column(Integer, nullable=False)
    well_type: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="sample"
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Dose value in the owning protocol's dose_unit. Unit not denormalized.
    dose: Mapped[float | None] = mapped_column(Float)

    plate: Mapped[PlateModel] = relationship("PlateModel", back_populates="wells")

    __table_args__ = (
        Index("ix_well_plate", "plate_id"),
    )


# ---------------------------------------------------------------------------
# Standalone data entities (not owned by Run aggregate)
# ---------------------------------------------------------------------------


class ReadoutDataModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Individual measurement point from a run."""

    __tablename__ = "readout_data"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("runs.id"), nullable=False
    )
    well_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    molecule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    readout_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("readout_definitions.id"), nullable=False
    )
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_qualifier: Mapped[str | None] = mapped_column(String(5))
    value_text: Mapped[str | None] = mapped_column(Text)
    is_outlier: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_computed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # Tags which normalization formula produced this row (NULL for raw rows).
    # Permits multiple computed rows per (well, readout_def) — one per formula —
    # when a readout def emits multiple views like %inh + z-score.
    normalization_applied: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        Index("ix_readout_data_run", "run_id"),
        Index("ix_readout_data_molecule", "molecule_id"),
        Index("ix_readout_data_definition", "readout_definition_id"),
    )


class DoseResponseCurveModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Fitted dose-response curve from screening run data."""

    __tablename__ = "dose_response_curves"

    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("runs.id"), nullable=False, index=True
    )
    curve_type: Mapped[str] = mapped_column(String(20), nullable=False)
    fitted_value: Mapped[float] = mapped_column(Float, nullable=False)
    hill_slope: Mapped[float] = mapped_column(Float, nullable=False)
    top: Mapped[float] = mapped_column(Float, nullable=False)
    bottom: Mapped[float] = mapped_column(Float, nullable=False)
    r_squared: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_interval_low: Mapped[float | None] = mapped_column(Float)
    confidence_interval_high: Mapped[float | None] = mapped_column(Float)
    num_points: Mapped[int] = mapped_column(Integer, nullable=False)
    curve_class: Mapped[str | None] = mapped_column(String(20))
    raw_data: Mapped[list | None] = mapped_column(JSONB)
    excluded_points: Mapped[list | None] = mapped_column(JSONB)
    fit_quality_warnings: Mapped[list | None] = mapped_column(JSONB)
    # Per-spec intercepts (IC50, IC90, ...) derived from the same Hill fit.
    # NULL on legacy rows; readers synthesize a single-element list from
    # (curve_type, fitted_value, ci_low, ci_high) when None.
    intercept_values: Mapped[list | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_drc_run", "run_id"),
        Index("ix_drc_molecule", "molecule_id"),
        Index("ix_drc_protocol", "protocol_id"),
    )


class RunImportTemplateModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Saved column mapping for long-format run-file imports."""

    __tablename__ = "run_import_templates"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index("ix_run_import_template_ws", "workspace_id"),
    )
