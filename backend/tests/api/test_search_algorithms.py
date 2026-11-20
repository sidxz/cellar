"""API tests for GET /api/v1/search/algorithms."""

from __future__ import annotations

from httpx import AsyncClient


class TestAlgorithmsEndpoint:
    async def test_algorithms_endpoint_returns_modes_and_algorithms(
        self, client: AsyncClient
    ) -> None:
        r = await client.get("/api/v1/search/algorithms")
        assert r.status_code == 200
        body = r.json()

        mode_algorithms = {m["name"]: m["algorithm"] for m in body["modes"]}
        assert set(mode_algorithms) == {"similar", "scaffold_hop", "fragment_in_target"}

        algorithm_names = {a["name"] for a in body["algorithms"]}
        assert algorithm_names == {"morgan", "fcfp"}
        assert set(mode_algorithms.values()) <= algorithm_names
