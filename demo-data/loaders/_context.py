"""Shared context for demo data loading."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from lagom import Container

DEFAULT_WORKSPACE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
DEMO_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d")

# Mutable — set by load.py before stages run. Loaders import this.
WORKSPACE_ID: uuid.UUID = DEFAULT_WORKSPACE_ID


@dataclass
class DemoAuthContext:
    """Satisfies AuthContext protocol via structural subtyping."""

    user_id: uuid.UUID = USER_ID
    workspace_id: uuid.UUID = DEFAULT_WORKSPACE_ID
    workspace_role: str = "admin"
    is_admin: bool = True
    accessible_project_ids: list[uuid.UUID] | None = None

    def has_role(self, minimum_role: str) -> bool:
        return True


@dataclass
class DemoContext:
    container: Container
    registry: IdRegistry
    data_dir: Path
    workspace_id: uuid.UUID = DEFAULT_WORKSPACE_ID
    auth: DemoAuthContext = field(default_factory=DemoAuthContext)

    def data(self, filename: str) -> dict:
        import json
        return json.loads((self.data_dir / filename).read_text())


class IdRegistry:
    """Maps local string keys to generated/returned UUIDs."""

    def __init__(self) -> None:
        self._map: dict[str, uuid.UUID] = {}

    def put(self, key: str, value: uuid.UUID) -> None:
        self._map[key] = value

    def get(self, key: str) -> uuid.UUID:
        return self._map[key]

    def has(self, key: str) -> bool:
        return key in self._map

    def get_optional(self, key: str | None) -> uuid.UUID | None:
        if key is None:
            return None
        return self._map.get(key)

    def deterministic(self, key: str) -> uuid.UUID:
        """Generate a deterministic UUID for entities without natural keys."""
        return uuid.uuid5(DEMO_NAMESPACE, key)
