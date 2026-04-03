"""SQLAlchemy declarative base and common column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""


class EntityModelMixin:
    """Common columns for all persistent entities (mirrors domain Entity)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceIdMixin:
    """Multi-tenant workspace scoping column."""

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)


class VersionMixin:
    """Optimistic concurrency control column."""

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
