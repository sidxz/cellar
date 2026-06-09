"""ProjectScopeStats — aggregate counts describing the size of a project's scope."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class ProjectScopeStats:
    molecule_count: int
    protocol_count: int
    run_count: int
    campaign_count: int = 0
    last_activity_at: datetime | None = None
    member_count: int = 0
    member_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)
