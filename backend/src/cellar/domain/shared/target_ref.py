"""Shared lightweight target reference VO.

Canonical home is ``domain.shared`` because ``TargetRef`` is consumed by more
than one bounded context's domain layer (``screening_assay`` defines targets;
``research_organization`` projects them onto campaigns). The bounded-context
independence contract requires such a shared type to live here rather than be
imported across contexts — mirroring the enum re-export convention in
``research_organization.enums``. ``screening_assay.target`` re-exports this name
for ergonomics and backward compatibility.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetRef:
    """Lightweight target reference for read models (grids, chips, run lists).

    Carries only what a display needs — never the full Target entity.
    """

    id: uuid.UUID
    name: str
    target_type: str
