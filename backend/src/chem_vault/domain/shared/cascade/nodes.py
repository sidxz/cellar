"""CascadeNode — preview tree node returned by Tier-2 preview."""
from __future__ import annotations

from dataclasses import dataclass, field

from chem_vault.domain.shared.cascade.actions import CascadeAction


@dataclass
class CascadeNode:
    entity_type: str
    table: str
    display_label: str
    count: int
    samples: list[dict]   # [{"id": str, "label": str | None}]
    truncated: bool
    action: CascadeAction
    children: list["CascadeNode"] = field(default_factory=list)
