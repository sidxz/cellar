"""Project membership domain types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class ProjectRole(StrEnum):
    """Role within a project. Ordered by ascending privilege."""

    VIEWER = "viewer"
    EDITOR = "editor"
    MANAGER = "manager"

    @property
    def level(self) -> int:
        return _ROLE_LEVELS[self]

    def has_at_least(self, minimum: ProjectRole) -> bool:
        return self.level >= minimum.level


_ROLE_LEVELS: dict[ProjectRole, int] = {
    ProjectRole.VIEWER: 0,
    ProjectRole.EDITOR: 1,
    ProjectRole.MANAGER: 2,
}


@dataclass(frozen=True)
class ProjectMember:
    """Value object — a user's membership in a project."""

    project_id: uuid.UUID
    user_id: uuid.UUID
    role: ProjectRole
