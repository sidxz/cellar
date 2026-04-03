"""Fake auth context for unit and integration tests."""

from __future__ import annotations

import uuid

_ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 0,
    "editor": 1,
    "admin": 2,
    "owner": 3,
}


class FakeAuth:
    """Satisfies the ``AuthContext`` protocol without network calls."""

    def __init__(
        self,
        *,
        role: str = "editor",
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        self._user_id = user_id or uuid.uuid4()
        self._workspace_id = workspace_id or uuid.uuid4()
        self.workspace_role = role

    @property
    def user_id(self) -> uuid.UUID:
        return self._user_id

    @property
    def workspace_id(self) -> uuid.UUID:
        return self._workspace_id

    @property
    def is_admin(self) -> bool:
        return self.workspace_role in ("admin", "owner")

    @property
    def is_editor(self) -> bool:
        return self.workspace_role in ("editor", "admin", "owner")

    def has_role(self, minimum_role: str) -> bool:
        return _ROLE_HIERARCHY.get(self.workspace_role, -1) >= _ROLE_HIERARCHY.get(
            minimum_role, 99
        )
