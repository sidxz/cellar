"""Butina clustering wrapper — returns per-compound cluster ids + per-cluster medoid index."""

from __future__ import annotations

from rdkit import DataStructs
from rdkit.ML.Cluster import Butina


class ButinaClusterer:
    """Threshold-based clustering on Tanimoto distance.

    Returns:
        clusters: list[int] of length n, mapping compound index -> cluster id.
        medoid_indices: list[int] of length cluster_count, first member of each cluster
            (RDKit Butina returns clusters as tuples where index 0 is the cluster centroid).
    """

    def __init__(self, *, threshold: float = 0.4) -> None:
        self._threshold = threshold

    def cluster(self, fingerprints: list) -> tuple[list[int], list[int]]:
        n = len(fingerprints)
        dists: list[float] = []
        for i in range(1, n):
            sims = DataStructs.BulkTanimotoSimilarity(fingerprints[i], fingerprints[:i])
            dists.extend(1.0 - s for s in sims)

        cluster_tuples = Butina.ClusterData(
            dists, n, self._threshold, isDistData=True
        )
        cluster_ids = [0] * n
        medoid_indices: list[int] = []
        for cid, members in enumerate(cluster_tuples):
            medoid_indices.append(members[0])
            for m in members:
                cluster_ids[m] = cid
        return cluster_ids, medoid_indices
