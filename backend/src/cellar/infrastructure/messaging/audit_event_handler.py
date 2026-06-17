"""Audit event handler — bridges EventDispatcher to AuditRecordingService.

Registered as a catch-all handler for DomainEvent. Each event dispatch
gets its own database session and transaction so audit records are
persisted independently of the use case's UoW.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.domain.shared.events import DomainEvent
from cellar.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
)

logger = structlog.get_logger(__name__)


class AuditEventHandler:
    """Catch-all event handler that creates audit records.

    Uses a dedicated session per event to ensure audit persistence
    is independent of the originating use case's transaction.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def __call__(self, event: DomainEvent) -> None:
        try:
            repo = SQLAlchemyAuditRepository(self._session_factory)
            service = AuditRecordingService(repo)
            await service.handle_event(event)
        except Exception:
            # Audit failure must not break the business operation.
            # Log and continue — the primary use case already committed.
            logger.exception(
                "audit.record_failed",
                event_type=type(event).__name__,
                aggregate_id=str(event.aggregate_id),
            )
