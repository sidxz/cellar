"""SQLAlchemy models for tags + per-entity link tables.

The unique index on (workspace_id, normalized_key, normalized_value) uses
``NULLS NOT DISTINCT`` (PG15+) so value-less tags dedup correctly. Trigram GIN
indexes back autocomplete. Each link table has real FKs with ON DELETE CASCADE.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class TagModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Tag registry — one row per distinct (key, optional value) per workspace."""

    __tablename__ = "tags"

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(String(256))
    normalized_key: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(256))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index(
            "uq_tags_ws_norm",
            "workspace_id",
            "normalized_key",
            "normalized_value",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_tags_norm_key_trgm",
            "normalized_key",
            postgresql_using="gin",
            postgresql_ops={"normalized_key": "gin_trgm_ops"},
        ),
        Index(
            "ix_tags_norm_value_trgm",
            "normalized_value",
            postgresql_using="gin",
            postgresql_ops={"normalized_value": "gin_trgm_ops"},
        ),
        Index("ix_tags_ws_created_by", "workspace_id", "created_by"),
    )


class TagLinkMixin:
    """Shared non-PK columns for every tag link table."""

    assigned_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MoleculeTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "molecule_tags"

    molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_molecule_tags_tag_id", "tag_id"),)


class ProtocolTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "protocol_tags"

    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_protocol_tags_tag_id", "tag_id"),)


class ProjectTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "project_tags"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_project_tags_tag_id", "tag_id"),)


class CollectionTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "collection_tags"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_collection_tags_tag_id", "tag_id"),)
