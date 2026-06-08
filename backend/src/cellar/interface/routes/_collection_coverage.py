"""Shared API response models for collection coverage (runs + protocols)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    EffectiveCollectionCoverage,
)


class CollectionCoverageResponse(BaseModel):
    """A run's coverage of one attached collection."""

    id: uuid.UUID
    name: str
    type: str
    covered: int
    total: int
    fraction: float | None

    @classmethod
    def from_coverage(cls, c: CollectionCoverage) -> CollectionCoverageResponse:
        return cls(
            id=c.ref.id,
            name=c.ref.name,
            type=c.ref.type,
            covered=c.covered,
            total=c.total,
            fraction=c.fraction,
        )


class EffectiveCollectionCoverageResponse(CollectionCoverageResponse):
    """Protocol rollup: adds the count of attaching runs."""

    run_count: int

    @classmethod
    def from_effective(cls, e: EffectiveCollectionCoverage) -> EffectiveCollectionCoverageResponse:
        return cls(
            id=e.ref.id,
            name=e.ref.name,
            type=e.ref.type,
            covered=e.covered,
            total=e.total,
            fraction=e.fraction,
            run_count=e.run_count,
        )
