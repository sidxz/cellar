"""SQLAlchemy model for CompoundFlag."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import Base


class CompoundFlagModel(Base):
    __tablename__ = "compound_flags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    protocol_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    flagged_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    flag_type: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

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
