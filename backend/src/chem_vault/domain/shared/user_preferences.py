"""User preferences — cross-device synced settings per user per workspace.

Not an AggregateRoot (no domain events, no optimistic concurrency).
Plain dataclass like audit models — simple CRUD entity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class UserPreferences:
    """User settings within a workspace."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    theme: str = "dark"
    sidebar_collapsed: bool = False
    default_search_columns: list[str] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@runtime_checkable
class UserPreferencesRepository(Protocol):
    """Repository protocol for user preferences."""

    async def get_by_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserPreferences | None: ...

    async def save(self, preferences: UserPreferences) -> UserPreferences: ...
