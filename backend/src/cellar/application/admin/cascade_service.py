"""Application-layer Protocol for cascade preview + execute.

Hides the SQLAlchemy session and the CascadeRunner concrete class from the
use case layer. Infrastructure provides ``UoWBackedCascadeService``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.shared.cascade import CascadeNode


@dataclass(frozen=True)
class InboundReference:
    """One group of rows still referencing the parent, found through an FK or a cascade rule."""

    table: str
    fk_column: str
    entity_type: str
    count: int
    samples: list[dict] = field(default_factory=list)
    truncated: bool = False
    display_label: str | None = None  # the rule's group label; None for a bare FK


class CascadeBlockedError(Exception):
    """A block rule matched, so the delete must not run. Carries every blocker."""

    def __init__(self, blockers: Sequence[InboundReference]) -> None:
        self.blockers = tuple(blockers)
        super().__init__(
            ", ".join(f"{b.count} {b.display_label or b.entity_type}" for b in self.blockers)
        )


@dataclass(frozen=True)
class CascadePreviewResult:
    """Tier-2 preview: a sampled tree of what goes, plus every blocker and warning."""

    root: CascadeNode
    blockers: list[InboundReference] = field(default_factory=list)
    warnings: list[InboundReference] = field(default_factory=list)


class CascadeService(Protocol):
    async def preview(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> CascadePreviewResult: ...

    async def execute(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[AuditEntry]:
        """Raises ``CascadeBlockedError`` when any block rule matches."""
        ...

    async def find_inbound_references(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[InboundReference]: ...

    async def fetch_typed_name_label(
        self,
        *,
        workspace_id: uuid.UUID,
        table: str,
        entity_id: uuid.UUID,
    ) -> str | None: ...
