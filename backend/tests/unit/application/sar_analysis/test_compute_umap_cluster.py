"""ComputeUmapCluster — orchestrates embed + cluster + pick.

Uses fakes for the FP loader so tests stay deterministic + fast."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID, uuid4

import pytest

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
)


@dataclass
class _FakeFp:
    bits: tuple[int, ...]


class _FakeFingerprintLoader:
    def __init__(self, items: dict[UUID, _FakeFp]) -> None:
        self._items = items

    async def load_morgan(self, ids: Iterable[UUID]) -> dict[UUID, object]:
        return {i: self._items[i] for i in ids if i in self._items}


class _FakeEmbedder:
    def embed(self, fps):
        # Just give each row coords = (row_index, 0).
        return [[float(i), 0.0] for i in range(len(fps))]


class _FakeButina:
    def cluster(self, fps, *, threshold=None):  # noqa: ARG002 (signature parity)
        # All in one cluster, medoid = 0.
        return [0] * len(fps), [0]


class _FakeMaxMin:
    def pick(self, fps, *, n):
        return list(range(min(n, len(fps))))


@pytest.mark.asyncio
async def test_compute_returns_full_result_payload() -> None:
    ids = [uuid4() for _ in range(12)]
    fps = {i: _FakeFp(bits=(0,) * 8) for i in ids}
    runner = ComputeUmapCluster(
        fingerprint_loader=_FakeFingerprintLoader(fps),
        embedder=_FakeEmbedder(),
        clusterer=_FakeButina(),
        maxmin_picker=_FakeMaxMin(),
    )
    out = await runner.execute(
        ComputeUmapClusterInput(
            molecule_ids=ids,
            picker="maxmin",
            picker_params={"n": 5},
        )
    )
    assert len(out.points) == 12
    assert out.cluster_count == 1
    assert len(out.representatives) == 5
    assert out.picker == "maxmin"


@pytest.mark.asyncio
async def test_compute_uses_butina_medoids_when_picker_butina() -> None:
    ids = [uuid4() for _ in range(8)]
    fps = {i: _FakeFp(bits=(0,) * 8) for i in ids}
    runner = ComputeUmapCluster(
        fingerprint_loader=_FakeFingerprintLoader(fps),
        embedder=_FakeEmbedder(),
        clusterer=_FakeButina(),
        maxmin_picker=_FakeMaxMin(),
    )
    out = await runner.execute(
        ComputeUmapClusterInput(
            molecule_ids=ids,
            picker="butina",
            picker_params={"threshold": 0.4},
        )
    )
    # With our fake butina, 1 cluster -> 1 medoid.
    assert len(out.representatives) == 1


@pytest.mark.asyncio
async def test_compute_skips_missing_fingerprints() -> None:
    ids = [uuid4() for _ in range(5)]
    # Only first 3 have fps.
    fps = {ids[0]: _FakeFp(()), ids[1]: _FakeFp(()), ids[2]: _FakeFp(())}
    runner = ComputeUmapCluster(
        fingerprint_loader=_FakeFingerprintLoader(fps),
        embedder=_FakeEmbedder(),
        clusterer=_FakeButina(),
        maxmin_picker=_FakeMaxMin(),
    )
    out = await runner.execute(
        ComputeUmapClusterInput(
            molecule_ids=ids,
            picker="maxmin",
            picker_params={"n": 2},
        )
    )
    assert len(out.points) == 3
    assert len(out.skipped_molecule_ids) == 2
