"""Pure dataclasses for the UMAP + cluster + picker result payload."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class UmapPoint:
    molecule_id: UUID
    x: float
    y: float


@dataclass(frozen=True)
class ClusterAssignment:
    molecule_id: UUID
    cluster_id: int


@dataclass(frozen=True)
class RepresentativePick:
    molecule_id: UUID
    cluster_id: int


@dataclass(frozen=True)
class UmapResult:
    points: list[UmapPoint]
    clusters: list[ClusterAssignment]
    representatives: list[RepresentativePick]
    cluster_count: int
    picker: str
    picker_params: dict[str, Any]
    skipped_molecule_ids: list[UUID] = field(default_factory=list)
