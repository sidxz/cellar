"""SQLAlchemy model for CompoundFlag."""

from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    WorkspaceIdMixin,
)


class CompoundFlagModel(Base, EntityModelMixin, WorkspaceIdMixin):
    __tablename__ = "compound_flags"

    molecule_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    protocol_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    flagged_by: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    flag_type: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "molecule_id",
            "protocol_id",
            "flagged_by",
            "flag_type",
            name="uq_compound_flag_unique",
        ),
        Index("ix_compound_flag_ws_protocol", "workspace_id", "protocol_id"),
        Index("ix_compound_flag_ws_molecule", "workspace_id", "molecule_id"),
    )
