"""Framework + cross-cutting deps and the generic use-case factory.

Split out of the legacy single-file ``cellar.interface.dependencies`` module.
Everything else in the package imports :func:`_get_use_case` from here.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import Depends, Request
from lagom import Container
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.inventory.salt_matcher import SaltMatcher
from cellar.application.shared.unit_of_work import (
    UnitOfWork,  # noqa: F401  (re-exported for compat)
)
from cellar.application.user.get_preferences import GetPreferences
from cellar.application.user.update_preferences import UpdatePreferences
from cellar.infrastructure.logging import bind_user_context
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry
from cellar.infrastructure.sentinel.auth import get_sentinel
from cellar.infrastructure.sentinel.org_directory import OrgDirectory
from cellar.infrastructure.sentinel.settings import SentinelSettings

__all__ = [
    "AuditServiceDep",
    "AuthDep",
    "EventDispatcherDep",
    "FingerprintRegistryDep",
    "GetPreferencesDep",
    "OrgDirectoryDep",
    "SaltMatcherUoWDep",
    "SessionFactoryDep",
    "UoWDep",
    "UpdatePreferencesDep",
    "_get_use_case",
    "get_audit_service",
    "get_auth",
    "get_container",
    "get_event_dispatcher",
    "get_org_directory",
    "get_preferences_command",
    "get_preferences_query",
    "get_salt_matcher_uow",
    "get_session_factory",
    "get_uow",
]


def get_container(request: Request) -> Container:
    """Retrieve the DI container from app state."""
    return request.app.state.container


def get_uow(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncUnitOfWork:
    """Request-scoped Unit of Work."""
    return container[AsyncUnitOfWork]


def get_session_factory(
    container: Annotated[Container, Depends(get_container)],
) -> async_sessionmaker:
    """Async session factory."""
    return container[async_sessionmaker]


def get_salt_matcher_uow(
    container: Annotated[Container, Depends(get_container)],
) -> tuple[SaltMatcher, AsyncUnitOfWork]:
    """Per-request ``SaltMatcher`` paired with its own ``AsyncUnitOfWork``.

    Returned as a tuple because the caller manages the UoW lifecycle —
    e.g. ``async with uow: ... await matcher.match_by_smiles(...)``. We
    can't bind the UoW into ``SaltMatcher`` at DI time and return just
    the matcher because the UoW must be entered/exited per call.
    """
    uow = AsyncUnitOfWork(container[async_sessionmaker])
    return SaltMatcher(SQLAlchemySaltEntryRepository(uow)), uow


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


# Sentinel auth dependency — stable wrapper so dependency_overrides work in tests.
# Lazy init: don't crash at import time if Sentinel env vars aren't set.
# Uses a reject-all stub when Sentinel is unavailable so auth is never bypassed.


async def _sentinel_not_configured() -> None:
    """Stub dependency that rejects all requests when Sentinel is not configured."""
    from fastapi import HTTPException

    raise HTTPException(
        status_code=503,
        detail="Sentinel auth not configured. Set SENTINEL_URL and SENTINEL_SERVICE_KEY.",
    )


# Sentinel is "configured" only when SENTINEL_SERVICE_KEY is explicitly set —
# the pydantic-settings default ("") is a missing-config signal, not a usable
# service key. The URL has a localhost default so dev still works; if you want
# prod fail-fast on missing URL too, set it explicitly in the deployment env.
_sentinel: object | None = None
if not os.environ.get("SENTINEL_SERVICE_KEY"):
    _sentinel_get_auth = _sentinel_not_configured
else:
    try:
        _sentinel = get_sentinel()
        _sentinel_get_auth = _sentinel.get_auth
    except (ValueError, ValidationError):
        # Sentinel env vars malformed — fall back to a reject-all stub. Any
        # other exception (import error, network, etc.) is a real bug and
        # must surface at startup.
        _sentinel = None
        _sentinel_get_auth = _sentinel_not_configured


# Sentinel org directory (read-only list of orgs for pickers/labels) — same
# "configured only if SENTINEL_SERVICE_KEY is set" guard as `_sentinel` above.
_org_directory: OrgDirectory | None = None
if _sentinel is not None:
    _settings = SentinelSettings()
    _org_directory = OrgDirectory(base_url=_settings.url, service_key=_settings.service_key)


def get_org_directory() -> OrgDirectory:
    if _org_directory is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Sentinel auth not configured.")
    return _org_directory


OrgDirectoryDep = Annotated[OrgDirectory, Depends(get_org_directory)]


async def get_auth(
    request: Request,
    auth: Annotated[Any, Depends(_sentinel_get_auth)],
) -> Any:
    """Stable auth dependency wrapper — overridable via dependency_overrides.

    Also binds the authenticated user/workspace into the logging context and
    onto ``request.state`` so the access-log line can include them.
    """
    user_id = getattr(auth, "user_id", None)
    workspace_id = getattr(auth, "workspace_id", None)
    user_id = str(user_id) if user_id is not None else None
    workspace_id = str(workspace_id) if workspace_id is not None else None
    bind_user_context(user_id=user_id, workspace_id=workspace_id)
    request.state.user_id = user_id
    request.state.workspace_id = workspace_id
    return auth


# Convenience type aliases for route handler signatures
AuthDep = Annotated[Any, Depends(get_auth)]
UoWDep = Annotated[AsyncUnitOfWork, Depends(get_uow)]
SessionFactoryDep = Annotated[async_sessionmaker, Depends(get_session_factory)]
SaltMatcherUoWDep = Annotated[tuple[SaltMatcher, AsyncUnitOfWork], Depends(get_salt_matcher_uow)]
EventDispatcherDep = Annotated[EventDispatcher, Depends(get_event_dispatcher)]
AuditServiceDep = Annotated[AuditRecordingService, Depends(get_audit_service)]
GetPreferencesDep = Annotated[GetPreferences, Depends(get_preferences_query)]
UpdatePreferencesDep = Annotated[UpdatePreferences, Depends(get_preferences_command)]


# --- Generic use-case dependency factory ---
def _get_use_case(uc_type: type):
    def _dep(container: Annotated[Container, Depends(get_container)]):
        return container[uc_type]

    return _dep


# --- Infrastructure singletons exposed to routes ---
FingerprintRegistryDep = Annotated[
    FingerprintRegistry, Depends(_get_use_case(FingerprintRegistry))
]
