"""API tests for the decomposition endpoints (POST /api/v1/sar/decomposition + jobs + rows).

Scope: route validation, DI wiring, an inline happy-path through HTTP, and 404s.
The join/sort/pagination internals are covered by the row-reader integration test.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


async def _seed_two_molecules(api_app, ws: uuid.UUID) -> list[uuid.UUID]:
    session_factory = api_app.state.container[async_sessionmaker]
    org_id = uuid.uuid4()
    ids = [uuid.uuid4(), uuid.uuid4()]
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, :n, 'internal', true, 1)"
            ),
            {"id": org_id, "ws": ws, "n": "org-sar"},
        )
        for mid, reg, smi in zip(ids, ("CV-A", "CV-B"), ("Fc1ccccc1", "Clc1ccccc1"), strict=True):
            await session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, name, "
                    "molecule_type, smiles, version, originating_org_id) VALUES "
                    "(:id, :ws, :r, :r, 'small_molecule', :smi, 1, :org)"
                ),
                {"id": mid, "ws": ws, "r": reg, "smi": smi, "org": org_id},
            )
        await session.commit()
    return ids


@pytest.mark.asyncio
async def test_rejects_both_inputs(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [], "collection_id": str(uuid.uuid4()), "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 400
    assert "exactly one" in res.json()["detail"]


@pytest.mark.asyncio
async def test_rejects_neither_input(client: AsyncClient) -> None:
    res = await client.post("/api/v1/sar/decomposition", json={"core_smiles": "c1ccccc1"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_rejects_empty_core(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/decomposition", json={"molecule_ids": [], "core_smiles": "   "}
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_empty_molecule_ids_returns_ready_empty_run(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/decomposition", json={"molecule_ids": [], "core_smiles": "c1ccccc1"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["total_count"] == 0
    assert body["rgroup_labels"] == []
    assert uuid.UUID(body["run_id"])


@pytest.mark.asyncio
async def test_inline_decomposition_then_rows(client, api_app, workspace_id) -> None:
    ids = await _seed_two_molecules(api_app, workspace_id)
    res = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["matched_count"] == 2
    assert body["total_count"] == 2
    assert body["rgroup_labels"]
    run_id = body["run_id"]

    rows_res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows", json={"offset": 0, "limit": 50}
    )
    assert rows_res.status_code == 200
    rows_body = rows_res.json()
    assert rows_body["total"] == 2
    assert {r["registration_number"] for r in rows_body["rows"]} == {"CV-A", "CV-B"}
    a_row = next(r for r in rows_body["rows"] if r["registration_number"] == "CV-A")
    assert a_row["smiles"] == "Fc1ccccc1"
    assert a_row["rgroups"]


@pytest.mark.asyncio
async def test_rows_sort_by_registration_number_desc(client, api_app, workspace_id) -> None:
    ids = await _seed_two_molecules(api_app, workspace_id)
    start = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    run_id = start.json()["run_id"]
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows",
        json={"sort": [{"col": "registration_number", "dir": "desc"}]},
    )
    assert [r["registration_number"] for r in res.json()["rows"]] == ["CV-B", "CV-A"]


@pytest.mark.asyncio
async def test_poll_inline_run_is_ready(client, api_app, workspace_id) -> None:
    ids = await _seed_two_molecules(api_app, workspace_id)
    start = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    run_id = start.json()["run_id"]
    poll = await client.get(f"/api/v1/sar/decomposition/jobs/{run_id}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_get_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.get(f"/api/v1/sar/decomposition/jobs/{uuid.uuid4()}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_cancel_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.post(f"/api/v1/sar/decomposition/jobs/{uuid.uuid4()}/cancel")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_rows_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.post(f"/api/v1/sar/decomposition/{uuid.uuid4()}/rows", json={})
    assert res.status_code == 404
