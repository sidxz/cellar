"""Pure-data result type for activity projection.

One ``ActivityScalar`` per molecule that has a value for the channel (sparse).
``snapshot`` is the molecule's full ``ActivityValue`` in wire shape (JSON-safe) so
heatmap curve-expand works without the client holding ``props.molecules``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ActivityScalar:
    molecule_id: UUID
    scalar: float
    unit: str | None
    qualifier: str | None
    source: str
    snapshot: dict[str, Any] = field(default_factory=dict)
