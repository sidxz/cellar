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
    def cluster(
        self, fingerprints, *, threshold: float | None = None
    ) -> tuple[list[int], list[int]]: ...


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

        # Always cluster (used for coloring even when picker=maxmin). The
        # cluster threshold is also a chemist knob — for MaxMin it controls
        # the color partition; for Butina it controls the picks too.
        cluster_threshold = float(payload.picker_params.get("threshold", 0.4))
        cluster_ids, medoid_indices = self._clusterer.cluster(
            fps, threshold=cluster_threshold
        )

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

    async def pick_only(
        self,
        *,
        existing: UmapResult,
        picker: str,
        picker_params: dict[str, Any],
    ) -> UmapResult:
        """Re-run the picker against a cached UMAP+cluster result.

        Skips the expensive UMAP step + Butina clustering by reusing the existing
        result's `points` and `clusters`. For MaxMin we still need fingerprints
        to compute Tanimoto distances; for Butina we just pick medoids out of
        the cached cluster assignments (no FP load required).

        Caller guarantees: existing.points / existing.clusters were computed at
        the same `threshold` the new picker_params specify (the partial-cache
        lookup keys on that).
        """
        # Cluster_id lookup per molecule, in the same order as existing.points.
        cluster_by_mol = {c.molecule_id: c.cluster_id for c in existing.clusters}
        ordered_ids = [p.molecule_id for p in existing.points]
        cluster_ids = [cluster_by_mol.get(mid, 0) for mid in ordered_ids]

        if picker == "maxmin":
            # Need real FPs for Tanimoto distance — load by ID.
            loaded = await self._loader.load_morgan(ordered_ids)
            fps = [loaded[i] for i in ordered_ids if i in loaded]
            if len(fps) != len(ordered_ids):
                # FP availability shifted since the cache was built — fall back
                # to the full path by raising. The caller can catch + redo.
                raise RuntimeError(
                    "Fingerprint availability changed since cache built; "
                    "cannot do pick-only path."
                )
            n = int(picker_params.get("n", 50))
            pick_indices = self._maxmin.pick(fps, n=n)
            rep_assignments = [(idx, cluster_ids[idx]) for idx in pick_indices]
        elif picker == "butina":
            # Medoid = first member of each cluster in the existing assignment.
            seen: dict[int, int] = {}
            for idx, cid in enumerate(cluster_ids):
                if cid not in seen:
                    seen[cid] = idx
            rep_assignments = sorted(
                ((idx, cid) for cid, idx in seen.items()), key=lambda x: x[1]
            )
        else:  # pragma: no cover - guarded at API layer
            raise ValueError(f"Unknown picker: {picker}")

        representatives = [
            RepresentativePick(molecule_id=ordered_ids[idx], cluster_id=cid)
            for idx, cid in rep_assignments
        ]

        return UmapResult(
            points=existing.points,
            clusters=existing.clusters,
            representatives=representatives,
            cluster_count=existing.cluster_count,
            picker=picker,
            picker_params=picker_params,
            skipped_molecule_ids=existing.skipped_molecule_ids,
        )
