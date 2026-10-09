"""An admin acting in a workspace, for application-level tests (same shape as the CLI loaders')."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class _Admin:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_role: str = "admin"
    org_id: uuid.UUID | None = None
    org_slug: str | None = None
    name: str = "test admin"
    email: str = ""
    is_admin: bool = True

    def has_role(self, minimum_role: str) -> bool:
        return True

    async def check_action(self, action: str) -> bool:
        return True


def admin_auth(workspace_id: uuid.UUID, user_id: uuid.UUID) -> _Admin:
    return _Admin(user_id=user_id, workspace_id=workspace_id)
