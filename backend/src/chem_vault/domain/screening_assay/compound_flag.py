"""CompoundFlag -- team-visible flag on a compound within a protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class FlagType(StrEnum):
    STAR = "star"
    OUTLIER = "outlier"
    FOLLOW_UP = "follow_up"


@dataclass
class CompoundFlag:
    """Not an AggregateRoot -- simple entity, no versioning.

    Flags are scoped to (workspace, molecule, protocol, user, flag_type).
    A user can flag the same compound in different protocols independently.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    molecule_id: uuid.UUID = field(default_factory=uuid.uuid4)
    protocol_id: uuid.UUID = field(default_factory=uuid.uuid4)
    flagged_by: uuid.UUID = field(default_factory=uuid.uuid4)
    flag_type: FlagType = FlagType.STAR
    note: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
