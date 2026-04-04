"""FastAPI dependency functions — resolve services from Lagom container.

Usage in route handlers::

    @router.post("/molecules")
    async def create_molecule(
        uow: UoWDep,
        dispatcher: EventDispatcherDep,
    ):
        ...
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from lagom import Container

from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.user.get_preferences import GetPreferences
from chem_vault.application.user.update_preferences import UpdatePreferences
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.sentinel.auth import get_sentinel


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


def get_preferences_query(
    container: Annotated[Container, Depends(get_container)],
) -> GetPreferences:
    """GetPreferences use case."""
    return container[GetPreferences]


def get_preferences_command(
    container: Annotated[Container, Depends(get_container)],
) -> UpdatePreferences:
    """UpdatePreferences use case."""
    return container[UpdatePreferences]


# Sentinel auth dependency — no circular import with app.py
_sentinel = get_sentinel()

# Convenience type aliases for route handler signatures
AuthDep = Annotated[Any, Depends(_sentinel.get_auth)]
UoWDep = Annotated[AsyncUnitOfWork, Depends(get_uow)]
EventDispatcherDep = Annotated[EventDispatcher, Depends(get_event_dispatcher)]
AuditServiceDep = Annotated[AuditRecordingService, Depends(get_audit_service)]
GetPreferencesDep = Annotated[GetPreferences, Depends(get_preferences_query)]
UpdatePreferencesDep = Annotated[UpdatePreferences, Depends(get_preferences_command)]
