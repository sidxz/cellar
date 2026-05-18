"""ComputeUmapCluster — pure runner: load FPs -> embed -> cluster -> pick.

Always runs Butina (used for color=cluster even when picker=maxmin).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Protocol
from uuid import UUID

import numpy as np

from cellar.domain.sar_analysis.umap_types import (
    ClusterAssignment,
    RepresentativePick,
    UmapPoint,
    UmapResult,
)


@dataclass(frozen=True)
class ComputeUmapClusterInput:
    molecule_ids: list[UUID]
    picker: str  # "maxmin" | "butina"
    picker_params: dict[str, Any]


class FingerprintLoader(Protocol):
    async def load_morgan(self, ids: Iterable[UUID]) -> dict[UUID, Any]: ...


class Embedder(Protocol):
    def embed(self, fingerprints) -> Any: ...


class Clusterer(Protocol):
    def cluster(self, fingerprints) -> tuple[list[int], list[int]]: ...


class MaxMinPickerProto(Protocol):
    def pick(self, fingerprints, *, n: int) -> list[int]: ...


def compute_ids_hash(ids: list[UUID]) -> str:
    h = hashlib.sha256()
    for i in sorted(str(x) for x in ids):
        h.update(i.encode())
    return h.hexdigest()


def compute_picker_param_hash(picker: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"picker": picker, "params": params}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class ComputeUmapCluster:
    def __init__(
        self,
        *,
        fingerprint_loader: FingerprintLoader,
        embedder: Embedder,
        clusterer: Clusterer,
        maxmin_picker: MaxMinPickerProto,
    ) -> None:
        self._loader = fingerprint_loader
        self._embedder = embedder
        self._clusterer = clusterer
        self._maxmin = maxmin_picker

    async def execute(self, payload: ComputeUmapClusterInput) -> UmapResult:
        loaded = await self._loader.load_morgan(payload.molecule_ids)
        ordered_ids = [i for i in payload.molecule_ids if i in loaded]
        skipped = [i for i in payload.molecule_ids if i not in loaded]
        if not ordered_ids:
            return UmapResult(
                points=[],
                clusters=[],
                representatives=[],
                cluster_count=0,
                picker=payload.picker,
                picker_params=payload.picker_params,
                skipped_molecule_ids=skipped,
            )

        fps = [loaded[i] for i in ordered_ids]

        # Embed -> 2D coords.
        embed_input = np.array([list(getattr(f, "bits", f)) for f in fps])
        coords = np.asarray(self._embedder.embed(embed_input))

        # Always cluster (used for coloring even when picker=maxmin).
        cluster_ids, medoid_indices = self._clusterer.cluster(fps)

        # Pick.
        if payload.picker == "maxmin":
            n = int(payload.picker_params.get("n", 50))
            pick_indices = self._maxmin.pick(fps, n=n)
            rep_assignments = [
                (idx, cluster_ids[idx]) for idx in pick_indices
            ]
        elif payload.picker == "butina":
            rep_assignments = [(idx, cluster_ids[idx]) for idx in medoid_indices]
        else:  # pragma: no cover - guarded at API layer
            raise ValueError(f"Unknown picker: {payload.picker}")

        points = [
            UmapPoint(molecule_id=mid, x=float(coords[i, 0]), y=float(coords[i, 1]))
            for i, mid in enumerate(ordered_ids)
        ]
        clusters = [
            ClusterAssignment(molecule_id=mid, cluster_id=cluster_ids[i])
            for i, mid in enumerate(ordered_ids)
        ]
        representatives = [
            RepresentativePick(molecule_id=ordered_ids[idx], cluster_id=cid)
            for idx, cid in rep_assignments
        ]

        return UmapResult(
            points=points,
            clusters=clusters,
            representatives=representatives,
            cluster_count=max(cluster_ids) + 1 if cluster_ids else 0,
            picker=payload.picker,
            picker_params=payload.picker_params,
            skipped_molecule_ids=skipped,
        )
