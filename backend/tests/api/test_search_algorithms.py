"""API tests for GET /api/v1/search/algorithms (T19)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestAlgorithmsEndpoint:
    async def test_algorithms_endpoint_returns_modes_and_algorithms(
        self, client: AsyncClient
    ) -> None:
        r = await client.get("/api/v1/search/algorithms")
        assert r.status_code == 200
        body = r.json()

        mode_names = {m["name"] for m in body["modes"]}
        assert mode_names == {"similar", "scaffold_hop", "fragment_in_target"}

        similar = next(m for m in body["modes"] if m["name"] == "similar")
        assert similar["algorithm"] == "morgan"
        assert similar["metric"] == "tanimoto"
        assert similar["default_threshold"] == 0.7
        assert similar["label"] == "Similar"
        assert similar["description"]

        algorithm_names = {a["name"] for a in body["algorithms"]}
        assert algorithm_names == {"morgan", "fcfp"}

    async def test_scaffold_hop_mode_present(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/search/algorithms")
        assert r.status_code == 200
        body = r.json()
        scaffold = next(m for m in body["modes"] if m["name"] == "scaffold_hop")
        assert scaffold["algorithm"] == "fcfp"
        assert scaffold["metric"] == "tanimoto"
        assert scaffold["default_threshold"] == 0.55

    async def test_fragment_in_target_mode_has_tversky_metric(
        self, client: AsyncClient
    ) -> None:
        r = await client.get("/api/v1/search/algorithms")
        assert r.status_code == 200
        body = r.json()
        frag = next(m for m in body["modes"] if m["name"] == "fragment_in_target")
        assert frag["metric"].startswith("tversky(")

    async def test_algorithms_have_descriptions(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/search/algorithms")
        assert r.status_code == 200
        body = r.json()
        for alg in body["algorithms"]:
            assert alg["description"], f"algorithm {alg['name']!r} has no description"
