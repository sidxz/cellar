"""API tests for POST /api/v1/sar/r-group-decomposition."""

# Scope: these API tests cover route validation + DI wiring only. The real
# decomposition chemistry is covered by unit tests in
# tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py and
# tests/unit/application/sar_analysis/test_decompose_rgroups.py.

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rejects_both_inputs(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={
            "molecule_ids": [],
            "collection_id": str(uuid.uuid4()),
            "core_smiles": "c1ccccc1",
        },
    )
    assert res.status_code == 400
    assert "exactly one" in res.json()["detail"]


@pytest.mark.asyncio
async def test_rejects_neither_input(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={"core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 400
    assert "exactly one" in res.json()["detail"]


@pytest.mark.asyncio
async def test_rejects_empty_core(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={"molecule_ids": [], "core_smiles": "   "},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_empty_molecule_ids_returns_empty_result(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={"molecule_ids": [], "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["core_smiles"] == "c1ccccc1"
    assert body["assignments"] == []
    assert body["unmatched_ids"] == []
    assert body["rgroup_labels"] == []
