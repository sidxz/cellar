"""UmapEmbedder unit tests — small-fingerprint golden + determinism."""

from __future__ import annotations

import numpy as np

from cellar.infrastructure.rdkit.umap_embedder import UmapEmbedder


def _make_random_bit_fps(n: int, dim: int = 2048, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 2, size=(n, dim), dtype=np.uint8)


def test_embedder_returns_shape_n_by_2() -> None:
    fps = _make_random_bit_fps(30)
    emb = UmapEmbedder()
    coords = emb.embed(fps)
    assert coords.shape == (30, 2)


def test_embedder_is_deterministic_with_fixed_seed() -> None:
    fps = _make_random_bit_fps(30)
    a = UmapEmbedder().embed(fps)
    b = UmapEmbedder().embed(fps)
    np.testing.assert_allclose(a, b)
