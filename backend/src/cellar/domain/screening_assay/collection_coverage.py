"""Collection-coverage read-model value objects for runs and protocols.

Coverage is derived (never persisted): how many of a collection's molecules a
run — or a protocol's attaching runs cumulatively — has screened. ``fraction``
is ``None`` for an empty collection (no divide-by-zero; surfaced as "—"). See
``docs/superpowers/specs/2026-06-07-run-collection-coverage-design.md``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionRef:
    """Lightweight collection reference for read models (chips, coverage bars).

    ``type`` is the collection-type enum value (e.g. ``"library"``), carried as
    a plain string so the screening read model needn't import the research-org
    enum.
    """

    id: uuid.UUID
    name: str
    type: str


@dataclass(frozen=True)
class CollectionCoverage:
    """A run's coverage of one attached collection."""

    ref: CollectionRef
    covered: int
    total: int

    @property
    def fraction(self) -> float | None:
        """Covered / total, or ``None`` when the collection is empty."""
        if self.total == 0:
            return None
        return self.covered / self.total


@dataclass(frozen=True)
class EffectiveCollectionCoverage:
    """A protocol's cumulative coverage of one collection across attaching runs."""

    ref: CollectionRef
    covered: int
    total: int
    run_count: int

    @property
    def fraction(self) -> float | None:
        if self.total == 0:
            return None
        return self.covered / self.total
