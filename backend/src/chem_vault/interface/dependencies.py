"""FastAPI dependency functions — resolve services from Lagom container.

Usage in route handlers::

    @router.post("/molecules")
    async def create_molecule(
        uow: Annotated[AsyncUnitOfWork, Depends(get_uow)],
        dispatcher: Annotated[EventDispatcher, Depends(get_event_dispatcher)],
    ):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from lagom import Container

from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def get_container(request: Request) -> Container:
    """Retrieve the DI container from app state."""
    return request.app.state.container


def get_uow(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncUnitOfWork:
    """Request-scoped Unit of Work."""
    return container[AsyncUnitOfWork]


def get_event_dispatcher(
    container: Annotated[Container, Depends(get_container)],
) -> EventDispatcher:
    """Singleton event dispatcher."""
    return container[EventDispatcher]


def get_audit_service(
    container: Annotated[Container, Depends(get_container)],
) -> AuditRecordingService:
    """Audit recording service."""
    return container[AuditRecordingService]


# Convenience type aliases for route handler signatures
UoWDep = Annotated[AsyncUnitOfWork, Depends(get_uow)]
EventDispatcherDep = Annotated[EventDispatcher, Depends(get_event_dispatcher)]
AuditServiceDep = Annotated[AuditRecordingService, Depends(get_audit_service)]
