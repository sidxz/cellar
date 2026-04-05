"""SQLAlchemy models for SynthesisRoute aggregate."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class SynthesisRouteModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Persistent model for SynthesisRoute aggregate root."""

    __tablename__ = "synthesis_routes"

    target_molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    route_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overall_yield: Mapped[float | None] = mapped_column(Float)
    estimated_cost_value: Mapped[float | None] = mapped_column(Float)
    estimated_cost_unit: Mapped[str | None] = mapped_column(String(30))
    scale: Mapped[str | None] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    # Relationship to owned ReactionStep entities
    steps: Mapped[list[ReactionStepModel]] = relationship(
        "ReactionStepModel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReactionStepModel.step_number",
        lazy="selectin",
    )


class ReactionStepModel(Base, EntityModelMixin):
    """Persistent model for ReactionStep owned entity."""

    __tablename__ = "reaction_steps"

    route_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("synthesis_routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_label: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(255))
    named_reaction: Mapped[str | None] = mapped_column(String(255))
    reaction_smiles: Mapped[str | None] = mapped_column(Text)
    reaction_smarts: Mapped[str | None] = mapped_column(Text)
    product_molecule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    product_description: Mapped[str | None] = mapped_column(Text)

    # ReactionConditions VO fields (flattened)
    condition_solvent: Mapped[str | None] = mapped_column(String(255))
    condition_temperature: Mapped[str | None] = mapped_column(String(100))
    condition_pressure: Mapped[str | None] = mapped_column(String(100))
    condition_catalyst: Mapped[str | None] = mapped_column(String(255))
    condition_atmosphere: Mapped[str | None] = mapped_column(String(100))
    condition_time: Mapped[str | None] = mapped_column(String(100))
    condition_additional: Mapped[dict | None] = mapped_column(JSONB)

    # ReactionOutcome VO fields (flattened)
    outcome_yield_percent: Mapped[float | None] = mapped_column(Float)
    outcome_crude_yield_percent: Mapped[float | None] = mapped_column(Float)
    outcome_purity_percent: Mapped[float | None] = mapped_column(Float)
    outcome_actual_scale_value: Mapped[float | None] = mapped_column(Float)
    outcome_actual_scale_unit: Mapped[str | None] = mapped_column(String(30))
    outcome_purification_method: Mapped[str | None] = mapped_column(String(255))

    # Reagents stored as JSONB list (each item is a ReactionReagent dict)
    reagents: Mapped[list | None] = mapped_column(JSONB, default=list)

    # DAG edges
    preceding_step_ids: Mapped[list | None] = mapped_column(JSONB, default=list)

    # Cross-context references
    eln_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    notes: Mapped[str | None] = mapped_column(Text)
