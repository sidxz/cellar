"""SQLAlchemy models for audit tables.

All three tables are append-only — the Alembic migration REVOKEs UPDATE and
DELETE at the database level.  These models therefore expose no ``update()``
helpers; INSERT is the only permitted DML.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cellar.infrastructure.persistence.sqlalchemy.base import Base


class AuditOperationModel(Base):
    __tablename__ = "audit_operations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="user")
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("audit_operations.id"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="completed")
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    entries: Mapped[list[AuditEntryModel]] = relationship(
        back_populates="operation", cascade="all, delete-orphan", lazy="selectin"
    )
    signature: Mapped[ElectronicSignatureModel | None] = relationship(
        back_populates="operation", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    __table_args__ = (
        Index("ix_audit_operations_entity", "entity_type", "entity_id"),
        Index("ix_audit_operations_user_id", "user_id"),
        Index("ix_audit_operations_correlation_id", "correlation_id"),
    )


class AuditEntryModel(Base):
    __tablename__ = "audit_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    operation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("audit_operations.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    field_name: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    operation: Mapped[AuditOperationModel] = relationship(back_populates="entries")

    __table_args__ = (Index("ix_audit_entries_entity", "entity_type", "entity_id"),)


class ElectronicSignatureModel(Base):
    __tablename__ = "electronic_signatures"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    operation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("audit_operations.id"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    auth_method: Mapped[str] = mapped_column(String(32), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    operation: Mapped[AuditOperationModel] = relationship(back_populates="signature")
