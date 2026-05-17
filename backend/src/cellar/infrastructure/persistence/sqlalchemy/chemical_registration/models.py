"""SQLAlchemy models for chemical registration context."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class MoleculeModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Molecule aggregate root — canonical compound within a workspace."""

    __tablename__ = "molecules"

    registration_number: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    molecule_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Structure (nullable for undisclosed)
    smiles: Mapped[str | None] = mapped_column(Text)
    cxsmiles: Mapped[str | None] = mapped_column(Text)
    inchi: Mapped[str | None] = mapped_column(Text)
    inchi_key: Mapped[str | None] = mapped_column(String(27))
    molfile: Mapped[str | None] = mapped_column(Text)

    # Descriptors (nullable for undisclosed)
    molecular_formula: Mapped[str | None] = mapped_column(String(100))
    molecular_weight: Mapped[float | None] = mapped_column(Float)
    exact_mass: Mapped[float | None] = mapped_column(Float)
    logp: Mapped[float | None] = mapped_column(Float)
    tpsa: Mapped[float | None] = mapped_column(Float)
    hbd: Mapped[int | None] = mapped_column(Integer)
    hba: Mapped[int | None] = mapped_column(Integer)
    rotatable_bonds: Mapped[int | None] = mapped_column(Integer)
    aromatic_rings: Mapped[int | None] = mapped_column(Integer)
    ring_count: Mapped[int | None] = mapped_column(Integer)
    heavy_atom_count: Mapped[int | None] = mapped_column(Integer)
    ro5_violations: Mapped[int | None] = mapped_column(Integer)

    # Predicted properties (individually nullable)
    logd: Mapped[float | None] = mapped_column(Float)
    pka: Mapped[float | None] = mapped_column(Float)
    logs: Mapped[float | None] = mapped_column(Float)
    prediction_source: Mapped[str | None] = mapped_column(String(100))
    predicted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Fingerprints (binary)
    fp_morgan: Mapped[bytes | None] = mapped_column(LargeBinary)

    # Scaffold (Bemis-Murcko; None = not computed, "" = acyclic)
    bemis_murcko_smiles: Mapped[str | None] = mapped_column(Text, nullable=True)

    # State machines
    structure_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="disclosed"
    )
    registration_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="approved"
    )
    synthesis_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="synthesized"
    )
    lifecycle_stage: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="registered"
    )

    # Other fields
    stereochemistry: Mapped[str | None] = mapped_column(String(20))
    sequence: Mapped[str | None] = mapped_column(Text)
    structure_image_key: Mapped[str | None] = mapped_column(String(500))
    tags: Mapped[list | None] = mapped_column(JSON)
    custom_fields: Mapped[dict | None] = mapped_column(JSON)
    invention_date: Mapped[date | None] = mapped_column(Date)
    disclosed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disclosed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    originating_org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), nullable=False
    )

    # Relationships
    identifiers: Mapped[list[MoleculeIdentifierModel]] = relationship(
        "MoleculeIdentifierModel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    mixture_components: Mapped[list[MixtureComponentModel]] = relationship(
        "MixtureComponentModel",
        cascade="all, delete-orphan",
        foreign_keys="MixtureComponentModel.mixture_molecule_id",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "registration_number", name="uq_mol_ws_regnum"),
        Index("ix_molecules_inchi_key", "workspace_id", "inchi_key"),
        Index("ix_molecules_merged_into_id", "merged_into_id"),
    )


class MoleculeIdentifierModel(Base, EntityModelMixin):
    """External/vendor identifiers mapped to a molecule."""

    __tablename__ = "molecule_identifiers"

    molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (UniqueConstraint("workspace_id", "identifier", name="uq_ws_identifier"),)


class MixtureComponentModel(Base, EntityModelMixin):
    """Component within a mixture molecule."""

    __tablename__ = "mixture_components"

    mixture_molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False
    )
    component_molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False
    )
    stoichiometric_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)


class MoleculeRelationshipModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Semantic relationships between molecules."""

    __tablename__ = "molecule_relationships"

    source_molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False
    )
    target_molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_molecule_id",
            "target_molecule_id",
            "relationship_type",
            name="uq_mol_rel",
        ),
    )
