"""SQLAlchemy model for user preferences — cross-device settings sync."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    WorkspaceIdMixin,
)


class UserPreferencesModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """Stores user preferences per workspace (theme, sidebar state, etc.)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_user_preferences_ws_user"),
    )
