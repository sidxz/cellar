"""Audit context bindings."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.audit.query_audit import GetAuditOperation, ListAuditOperations
from cellar.domain.audit_compliance.repository import AuditRepository
from cellar.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
)


def register_audit(container: Container) -> None:
    # Force cascade rules to register at DI bootstrap.
    import cellar.infrastructure.cascade.rules_audit_compliance  # noqa: F401

    container.define(
        SQLAlchemyAuditRepository,
        lambda c: SQLAlchemyAuditRepository(c[async_sessionmaker]),
    )
    container.define(AuditRepository, lambda c: c[SQLAlchemyAuditRepository])
    container.define(
        AuditRecordingService,
        lambda c: AuditRecordingService(c[AuditRepository]),
    )
    container.define(
        ListAuditOperations,
        lambda c: ListAuditOperations(c[AuditRepository]),
    )
    container.define(
        GetAuditOperation,
        lambda c: GetAuditOperation(c[AuditRepository]),
    )
