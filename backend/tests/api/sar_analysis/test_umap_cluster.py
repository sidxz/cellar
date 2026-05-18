"""API tests for POST /api/v1/sar/umap-cluster + GET/cancel job endpoints.

The heavy compute test (test_returns_inline_result_for_small_set) uses a
lightweight stub for StartUmapClusterJob so it doesn't require seeded
molecules with real Morgan fingerprints in the test DB.  All validation /
shape tests run against the real container.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from cellar.application.sar_analysis.start_umap_cluster_job import (
    StartUmapClusterJobOutput,
)
from cellar.domain.sar_analysis.umap_types import (
    ClusterAssignment,
    RepresentativePick,
    UmapPoint,
    UmapResult,
)
from cellar.interface.dependencies._sar_analysis import _get_start_umap_cluster_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_MOL_IDS = [uuid.uuid4() for _ in range(20)]

_FAKE_RESULT = UmapResult(
    points=[UmapPoint(molecule_id=mid, x=float(i), y=float(-i)) for i, mid in enumerate(_FAKE_MOL_IDS)],
    clusters=[ClusterAssignment(molecule_id=mid, cluster_id=i % 5) for i, mid in enumerate(_FAKE_MOL_IDS)],
    representatives=[
        RepresentativePick(molecule_id=_FAKE_MOL_IDS[i * 4], cluster_id=i) for i in range(5)
    ],
    cluster_count=5,
    picker="maxmin",
    picker_params={"n": 5},
    skipped_molecule_ids=[],
)


class _StubStartUmapClusterJob:
    """Stub that always returns an inline result without touching the DB."""

    async def execute(self, payload: Any) -> StartUmapClusterJobOutput:
        return StartUmapClusterJobOutput(result=_FAKE_RESULT, job=None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def umap_client(api_app: Any) -> AsyncIterator[AsyncClient]:
    """Client with the StartUmapClusterJob use case stubbed out.

    This avoids the need for seeded molecules with real Morgan fingerprints.
    The stub returns a canned UmapResult with 20 points + 5 representatives.
    """
    # Override via dependency_overrides — same mechanism used elsewhere in
    # the test suite (e.g. get_auth override in conftest.py).
    api_app.dependency_overrides[_get_start_umap_cluster_job] = lambda: _StubStartUmapClusterJob()

    transport = ASGITransport(app=api_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up override
    api_app.dependency_overrides.pop(_get_start_umap_cluster_job, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_inline_result_for_small_set(umap_client: AsyncClient) -> None:
    """Inline result (200) is returned for a small mol set (stub bypasses compute)."""
    resp = await umap_client.post(
        "/api/v1/sar/umap-cluster",
        json={
            "molecule_ids": [str(m) for m in _FAKE_MOL_IDS],
            "picker": "maxmin",
            "n": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job"] is None
    assert body["result"] is not None
    assert len(body["result"]["points"]) == 20
    assert len(body["result"]["representatives"]) == 5


@pytest.mark.asyncio
async def test_rejects_below_minimum_size(client: AsyncClient) -> None:
    """400 when fewer than 10 molecules are supplied (size check before any compute)."""
    mol_ids = [str(uuid.uuid4()) for _ in range(5)]
    resp = await client.post(
        "/api/v1/sar/umap-cluster",
        json={"molecule_ids": mol_ids, "picker": "maxmin", "n": 2},
    )
    assert resp.status_code == 400
    assert "10" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_rejects_above_max_size(client: AsyncClient) -> None:
    """400 when more than 50000 molecules are supplied (size check fires before DB reads)."""
    mol_ids = [str(uuid.uuid4()) for _ in range(50_001)]
    resp = await client.post(
        "/api/v1/sar/umap-cluster",
        json={"molecule_ids": mol_ids, "picker": "maxmin", "n": 50},
    )
    assert resp.status_code == 400
    assert "50000" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_requires_n_when_maxmin(client: AsyncClient) -> None:
    """422 when picker=maxmin and n is omitted (Pydantic model_validator)."""
    mol_ids = [str(uuid.uuid4()) for _ in range(20)]
    resp = await client.post(
        "/api/v1/sar/umap-cluster",
        json={"molecule_ids": mol_ids, "picker": "maxmin"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_returns_404_for_missing_job(client: AsyncClient) -> None:
    """404 when polling for a job ID that does not exist."""
    resp = await client.get(f"/api/v1/sar/umap-cluster/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
