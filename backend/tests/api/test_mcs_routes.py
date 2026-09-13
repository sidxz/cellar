"""API tests for POST /api/v1/sar/mcs.

Unlike its scaffold-tree and umap-cluster siblings this endpoint answers
inline, so there are no job, poll or cancel routes to cover — see ComputeMcs
for why.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

SERIES = [
    "Cc1ccc2ncc(C(=O)O)c(N)c2c1",
    "Clc1ccc2ncc(C(=O)O)c(NC)c2c1",
    "COc1ccc2ncc(C(=O)O)c(N)c2c1",
]


_ORG_ID_CACHE: dict[int, str] = {}


async def _org(client: AsyncClient) -> str:
    key = id(client)
    if key not in _ORG_ID_CACHE:
        res = await client.post(
            "/api/v1/organizations", json={"name": "TestOrg", "org_type": "internal"}
        )
        assert res.status_code == 201, res.text
        _ORG_ID_CACHE[key] = res.json()["id"]
    return _ORG_ID_CACHE[key]


async def _register(client: AsyncClient, smiles: str, name: str) -> str:
    res = await client.post(
        "/api/v1/molecules",
        json={"smiles": smiles, "name": name, "originating_org_id": await _org(client)},
    )
    assert res.status_code == 201, res.text
    return res.json()["molecule"]["id"]


@pytest.mark.asyncio
async def test_returns_the_shared_core_of_a_series(client: AsyncClient) -> None:
    ids = [await _register(client, smi, f"mcs-{i}") for i, smi in enumerate(SERIES)]

    res = await client.post("/api/v1/sar/mcs", json={"molecule_ids": ids})

    assert res.status_code == 200, res.text
    body = res.json()
    # The envelope matches the other two SAR computes; this one never defers.
    assert body["job"] is None
    result = body["result"]
    assert result["molecule_count"] == 3
    assert result["timed_out"] is False
    assert result["num_atoms"] == 14
    assert result["num_bonds"] == 15
    assert result["smarts"].startswith("[#")
    # Plain SMILES, so it can go straight to /molecules/depict or to R-group
    # decomposition's core_smiles.
    assert result["core_smiles"] == "Nc1c(C(=O)O)cnc2ccccc12"


@pytest.mark.xfail(
    reason=(
        "POST /molecules/depict is a 500 on main — the route passes a workspace_id "
        "the query does not declare. See docs/backlog/molecules-depict-500.md; this "
        "passes as soon as that one-liner lands."
    ),
)
@pytest.mark.asyncio
async def test_the_core_is_depictable(client: AsyncClient) -> None:
    ids = [await _register(client, smi, f"mcs-depict-{i}") for i, smi in enumerate(SERIES)]
    core = (await client.post("/api/v1/sar/mcs", json={"molecule_ids": ids})).json()["result"][
        "core_smiles"
    ]

    res = await client.post("/api/v1/molecules/depict", json={"smiles_list": [core]})

    assert res.status_code == 200, res.text
    # Depiction silently skips SMILES it cannot parse, so a rendered image is
    # the proof that core_smiles is genuinely usable downstream.
    assert core in res.json()["images"]


@pytest.mark.asyncio
async def test_rejects_both_inputs_or_neither(client: AsyncClient) -> None:
    both = await client.post(
        "/api/v1/sar/mcs",
        json={"molecule_ids": [str(uuid.uuid4())], "collection_id": str(uuid.uuid4())},
    )
    assert both.status_code == 422, both.text

    neither = await client.post("/api/v1/sar/mcs", json={})
    assert neither.status_code == 422, neither.text


@pytest.mark.asyncio
async def test_rejects_a_set_too_small_to_have_a_common_substructure(
    client: AsyncClient,
) -> None:
    res = await client.post("/api/v1/sar/mcs", json={"molecule_ids": [str(uuid.uuid4())]})

    assert res.status_code == 400, res.text
    assert "at least 2" in res.json()["detail"]


@pytest.mark.asyncio
async def test_unknown_collection_id_is_404(client: AsyncClient) -> None:
    res = await client.post("/api/v1/sar/mcs", json={"collection_id": str(uuid.uuid4())})

    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_unknown_molecule_ids_answer_about_nothing(client: AsyncClient) -> None:
    # Ids the workspace doesn't own drop out of the fetch rather than erroring;
    # molecule_count says the answer covers none of them.
    res = await client.post(
        "/api/v1/sar/mcs",
        json={"molecule_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
    )

    assert res.status_code == 200, res.text
    result = res.json()["result"]
    assert result["molecule_count"] == 0
    assert result["num_atoms"] == 0
    assert result["core_smiles"] is None
