"""Application-layer auth context protocol and guards.

The ``AuthContext`` protocol defines what the application layer needs from auth
without depending on Sentinel SDK types. Infrastructure adapts ``RequestAuth``
to satisfy this protocol (structural subtyping).
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.research_organization.project_membership import ProjectRole
from cellar.domain.shared.errors import AuthorizationError, NotFoundError


@runtime_checkable
class AuthContext(Protocol):
    """Auth context available to use cases. Satisfied by Sentinel's RequestAuth."""

    @property
    def user_id(self) -> uuid.UUID: ...

    @property
    def workspace_id(self) -> uuid.UUID: ...

    @property
    def workspace_role(self) -> str: ...

    @property
    def is_admin(self) -> bool: ...

    def has_role(self, minimum_role: str) -> bool: ...


# ---------------------------------------------------------------------------
# Guards — raise AuthorizationError on failure
# ---------------------------------------------------------------------------


def require_workspace_role(auth: AuthContext | None, minimum_role: str) -> None:
    """Raise if auth is present but lacks the required workspace role."""
    if auth is None:
        return  # Workers / system calls bypass
    if not auth.has_role(minimum_role):
        raise AuthorizationError(
            f"Requires at least '{minimum_role}' role",
            detail=f"Current role: '{auth.workspace_role}'",
        )


def require_editor(auth: AuthContext | None) -> None:
    """Shorthand: require at least editor role."""
    require_workspace_role(auth, "editor")


def require_admin(auth: AuthContext | None) -> None:
    """Shorthand: require at least admin role."""
    require_workspace_role(auth, "admin")


def require_same_workspace(auth: AuthContext | None, workspace_id: uuid.UUID | None) -> None:
    """Raise if the entity belongs to a different workspace.

    Returns NotFoundError-style message to avoid leaking entity existence.
    """
    if auth is None:
        return  # Workers / system calls bypass
    if workspace_id is None:
        raise AuthorizationError("workspace_id must not be None")
    if auth.workspace_id != workspace_id:
        raise NotFoundError("Entity")


@runtime_checkable
class ProjectAccessContext(Protocol):
    """Extended auth with project-level access info."""

    @property
    def accessible_project_ids(self) -> list[uuid.UUID] | None:
        """None = admin bypass, [] = no projects, [ids] = specific projects."""
        ...


def require_project_role(
    auth: AuthContext | None,
    user_role: ProjectRole | None,
    minimum_role: ProjectRole,
) -> None:
    """Raise if the user lacks the required project role.

    Admins bypass project-role checks.
    """
    if auth is None:
        return  # System calls bypass
    if auth.is_admin:
        return  # Admins bypass
    if user_role is None:
        raise AuthorizationError(
            "Not a member of this project",
            detail="You must be added to this project to perform this action.",
        )
    if not user_role.has_at_least(minimum_role):
        raise AuthorizationError(
            f"Requires at least '{minimum_role.value}' project role",
            detail=f"Current project role: '{user_role.value}'",
        )
