"""SQLAlchemy model for CDD molecule sync tracking records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    WorkspaceIdMixin,
)


class CddMoleculeSyncModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Tracks which CDD molecule IDs map to local molecule IDs."""

    __tablename__ = "cdd_molecule_sync"

    cdd_vault_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cdd_molecule_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id"), nullable=False
    )
    cdd_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "cdd_vault_id",
            "cdd_molecule_id",
            name="uq_cdd_sync_ws_vault_mol",
        ),
        Index("ix_cdd_mol_sync_ws_vault", "workspace_id", "cdd_vault_id"),
        Index("ix_cdd_mol_sync_molecule", "molecule_id"),
    )
