"""SQLAlchemy model for the Personalization context."""

from __future__ import annotations

import uuid

from sqlalchemy import Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class FavoriteModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """A user's favorite (pin) of an entity — soft polymorphic reference."""

    __tablename__ = "favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index(
            "uq_favorites_user_entity",
            "user_id",
            "workspace_id",
            "entity_type",
            "entity_id",
            unique=True,
        ),
        Index("ix_favorites_user_type", "user_id", "workspace_id", "entity_type"),
    )
