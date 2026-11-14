"""SQLAlchemy models for the Personalization context."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
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
            "uq_favorites_ws_user_entity",
            "workspace_id",
            "user_id",
            "entity_type",
            "entity_id",
            unique=True,
        ),
    )


class RecentSearchModel(Base, EntityModelMixin, WorkspaceIdMixin):
    """A search a user ran — one row per distinct search, newest ``ran_at`` wins.

    ``query`` / ``columns`` mirror ``saved_searches``: a migration that rewrites
    a stored search value (e.g. an aggregation rule rename) covers both tables.
    """

    __tablename__ = "recent_searches"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    query_key: Mapped[str] = mapped_column(String(64), nullable=False)
    query: Mapped[dict] = mapped_column(JSONB, nullable=False)
    columns: Mapped[dict | None] = mapped_column(JSONB)
    result_count: Mapped[int | None] = mapped_column(Integer)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_recent_searches_ws_user_key",
            "workspace_id",
            "user_id",
            "query_key",
            unique=True,
        ),
        Index("ix_recent_searches_ws_user_ran", "workspace_id", "user_id", "ran_at"),
    )
