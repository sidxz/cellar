"""Application-layer auth context protocol and guards.

The ``AuthContext`` protocol defines what the application layer needs from auth
without depending on Duar SDK types. Infrastructure adapts ``RequestAuth``
to satisfy this protocol (structural subtyping).
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from cellar.domain.research_organization.project_membership import ProjectRole
from cellar.domain.shared.errors import AuthorizationError, NotFoundError


@runtime_checkable
class AuthContext(Protocol):
    """Auth context available to use cases. Satisfied by Duar's RequestAuth."""

    @property
    def user_id(self) -> uuid.UUID: ...

    @property
    def workspace_id(self) -> uuid.UUID: ...

    @property
    def workspace_role(self) -> str: ...

    @property
    def org_id(self) -> uuid.UUID | None: ...

    @property
    def org_slug(self) -> str | None: ...

    @property
    def name(self) -> str: ...

    @property
    def email(self) -> str: ...

    @property
    def is_admin(self) -> bool: ...

    def has_role(self, minimum_role: str) -> bool: ...

    async def check_action(self, action: str) -> bool:
        """Check a fine-grained RBAC action grant (Duar SDK dedupes per request)."""
        ...

    async def list_members(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Members of the current workspace (``user_id`` as a string); no limit = all."""
        ...


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


LOAN_APPROVE_ACTION = "cellar:approve_loan"


async def require_loan_authority(auth: AuthContext | None, owner_org_id: uuid.UUID) -> None:
    """Owner-side loan verbs (approve/deny/confirm-out/confirm-in).

    Admin/owner bypasses everything (also dodges the ungranted-action
    deadlock — no Duar grants exist until an operator assigns them).
    Otherwise: editor in the OWNER org holding the cellar:approve_loan
    RBAC action — the first runtime check_action call in this codebase.
    """
    require_authenticated(auth)
    require_editor(auth)
    assert auth is not None  # require_authenticated raised otherwise
    if auth.is_admin:
        return
    if auth.org_id != owner_org_id:
        raise AuthorizationError("Only the owner organization can manage this loan")
    if not await auth.check_action(LOAN_APPROVE_ACTION):
        raise AuthorizationError("Missing loan approval permission")


def require_authenticated(auth: AuthContext | None) -> None:
    """Raise if no user identity is present.

    For use cases that record the acting user (``created_by``, ``approved_by``,
    ``locked_by``, …) — these cannot run as system calls, so ``auth=None`` is
    rejected instead of bypassed.
    """
    if auth is None:
        raise AuthorizationError("Authentication required")


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


def require_same_user(auth: AuthContext | None, user_id: uuid.UUID) -> None:
    """Raise if acting on another user's personal data.

    For per-user-owned resources (favorites, …) where ``user_id`` is the
    ownership key, not provenance metadata. Workers / system calls bypass.
    """
    if auth is None:
        return  # Workers / system calls bypass
    if auth.user_id != user_id:
        raise AuthorizationError("Cannot act on another user's personal data")


def require_admin_or_user(auth: AuthContext | None, user_id: uuid.UUID | None) -> None:
    """Raise unless the caller is a workspace admin or is ``user_id`` (a record's creator).

    A record with no creator on file (``None``) can only be changed by an admin.
    Workers / system calls bypass.
    """
    if auth is None or auth.is_admin:
        return
    if user_id is None or auth.user_id != user_id:
        raise AuthorizationError("Only an admin or the person who created it can change this")


async def is_workspace_member(auth: AuthContext, user_id: uuid.UUID) -> bool:
    """Whether ``user_id`` is a current member of the caller's workspace."""
    wanted = str(user_id)
    return any(str(m.get("user_id")) == wanted for m in await auth.list_members(limit=None))


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
