"""Audit event handler — bridges EventDispatcher to AuditRecordingService.

Registered as a catch-all handler for DomainEvent. Each event dispatch
gets its own database session and transaction so audit records are
persisted independently of the use case's UoW.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
)

logger = logging.getLogger(__name__)


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
                "Failed to record audit for %s (aggregate=%s)",
                type(event).__name__,
                event.aggregate_id,
            )
