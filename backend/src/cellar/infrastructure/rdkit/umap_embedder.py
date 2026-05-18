"""UMAP embedding wrapper — Tanimoto-equivalent jaccard metric on binary FPs.

Pinned defaults: n_neighbors=15, min_dist=0.1, metric=jaccard, random_state=42.
"""

from __future__ import annotations

import numpy as np
import umap


class UmapEmbedder:
    """Thin wrapper around umap-learn with cheminformatics defaults locked.

    Defaults intentionally not user-tunable in V3 (see spec §3).
    """

    def __init__(
        self,
        *,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "jaccard",
        random_state: int = 42,
    ) -> None:
        self._n_neighbors = n_neighbors
        self._min_dist = min_dist
        self._metric = metric
        self._random_state = random_state

    def embed(self, fingerprints: np.ndarray) -> np.ndarray:
        """Embed a stack of binary fingerprints to 2D coords.

        Caller is responsible for ensuring at least 10 rows (spec §4.8).
        """
        effective_neighbors = min(self._n_neighbors, max(2, fingerprints.shape[0] - 1))
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=effective_neighbors,
            min_dist=self._min_dist,
            metric=self._metric,
            random_state=self._random_state,
        )
        return reducer.fit_transform(fingerprints)
