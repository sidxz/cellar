"""Tests for UMAP cluster result dataclasses."""

from __future__ import annotations

from uuid import uuid4

from cellar.domain.sar_analysis.umap_types import (
    ClusterAssignment,
    RepresentativePick,
    UmapPoint,
    UmapResult,
)


def test_umap_point_round_trip() -> None:
    mid = uuid4()
    p = UmapPoint(molecule_id=mid, x=1.5, y=-0.3)
    assert p.molecule_id == mid
    assert p.x == 1.5
    assert p.y == -0.3


def test_umap_result_carries_full_payload() -> None:
    m1, m2 = uuid4(), uuid4()
    result = UmapResult(
        points=[UmapPoint(m1, 0.0, 0.0), UmapPoint(m2, 1.0, 1.0)],
        clusters=[ClusterAssignment(m1, 0), ClusterAssignment(m2, 1)],
        representatives=[RepresentativePick(m1, 0)],
        cluster_count=2,
        picker="maxmin",
        picker_params={"n": 1},
        skipped_molecule_ids=[],
    )
    assert len(result.points) == 2
    assert result.cluster_count == 2
    assert result.picker == "maxmin"
