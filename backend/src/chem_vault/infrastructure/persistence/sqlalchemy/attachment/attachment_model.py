"""SQLAlchemy model for Attachment."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class AttachmentModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "attachments"

    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    attachable_type: Mapped[str] = mapped_column(String(50), nullable=False)
    attachable_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index("ix_attachments_entity", "attachable_type", "attachable_id"),
        UniqueConstraint(
            "workspace_id",
            "attachable_type",
            "attachable_id",
            "file_name",
            name="uq_attachment_entity_filename",
        ),
    )
