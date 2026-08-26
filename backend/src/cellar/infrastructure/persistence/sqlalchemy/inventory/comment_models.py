"""ORM model for plate_comments (spec 2026-08-25 §7.2)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class CommentModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Polymorphic target (no FK on target_id — same stance as plate_loan_items.plate_id);
    loan_id is a real FK so a deleted loan just detaches its comments."""

    __tablename__ = "plate_comments"

    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    loan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("plate_loans.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (
        Index(
            "ix_plate_comments_ws_target",
            "workspace_id",
            "target_type",
            "target_id",
            "created_at",
        ),
        Index("ix_plate_comments_ws_loan", "workspace_id", "loan_id"),
    )
