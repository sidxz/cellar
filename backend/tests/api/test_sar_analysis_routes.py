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


# Structure + descriptor data for the two seed molecules.
# All ChemicalStructure fields (smiles/cxsmiles/inchi/inchi_key/molfile) and all
# ComputedDescriptors fields must be populated together — the domain enforces all-or-nothing.
_MOLECULE_DATA = [
    {
        "reg": "CV-A",
        "smiles": "Fc1ccccc1",
        "cxsmiles": "Fc1ccccc1",
        "inchi": "InChI=1S/C6H5F/c7-6-4-2-1-3-5-6/h1-5H",
        "inchi_key": "ANSXAPMBZXGWNI-UHFFFAOYSA-N",
        "molfile": "\n     RDKit          2D\n\n  7  7  0  0  0  0  0  0  0  0999 V2000\n    1.5000    0.0000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -0.7500   -1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -2.2500   -1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -3.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -2.2500    1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -0.7500    1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n  1  2  1  0\n  2  3  2  0\n  3  4  1  0\n  4  5  2  0\n  5  6  1  0\n  6  7  2  0\n  7  2  1  0\nM  END\n",
        "molecular_formula": "C6H5F",
        "molecular_weight": 96.1,
        "exact_mass": 96.038,
        "logp": 2.27,
        "tpsa": 0.0,
        "hbd": 0,
        "hba": 1,
        "rotatable_bonds": 0,
        "aromatic_rings": 1,
        "ring_count": 1,
        "heavy_atom_count": 7,
        "ro5_violations": 0,
    },
    {
        "reg": "CV-B",
        "smiles": "Clc1ccccc1",
        "cxsmiles": "Clc1ccccc1",
        "inchi": "InChI=1S/C6H5Cl/c7-6-4-2-1-3-5-6/h1-5H",
        "inchi_key": "MVPPADPHJFYWMZ-UHFFFAOYSA-N",
        "molfile": "\n     RDKit          2D\n\n  7  7  0  0  0  0  0  0  0  0999 V2000\n    1.5000    0.0000    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -0.7500   -1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -2.2500   -1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -3.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -2.2500    1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n   -0.7500    1.2990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n  1  2  1  0\n  2  3  2  0\n  3  4  1  0\n  4  5  2  0\n  5  6  1  0\n  6  7  2  0\n  7  2  1  0\nM  END\n",
        "molecular_formula": "C6H5Cl",
        "molecular_weight": 112.56,
        "exact_mass": 111.999,
        "logp": 2.84,
        "tpsa": 0.0,
        "hbd": 0,
        "hba": 0,
        "rotatable_bonds": 0,
        "aromatic_rings": 1,
        "ring_count": 1,
        "heavy_atom_count": 7,
        "ro5_violations": 0,
    },
]


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
        for mid, mol in zip(ids, _MOLECULE_DATA, strict=True):
            await session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, name, "
                    "molecule_type, smiles, cxsmiles, inchi, inchi_key, molfile, "
                    "molecular_formula, molecular_weight, exact_mass, logp, tpsa, "
                    "hbd, hba, rotatable_bonds, aromatic_rings, ring_count, "
                    "heavy_atom_count, ro5_violations, version, originating_org_id) VALUES "
                    "(:id, :ws, :r, :r, 'small_molecule', :smiles, :cxsmiles, :inchi, "
                    ":inchi_key, :molfile, :molecular_formula, :molecular_weight, "
                    ":exact_mass, :logp, :tpsa, :hbd, :hba, :rotatable_bonds, "
                    ":aromatic_rings, :ring_count, :heavy_atom_count, :ro5_violations, "
                    "1, :org)"
                ),
                {"id": mid, "ws": ws, "r": mol["reg"], "org": org_id, **mol},
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


async def _ready_run_id(client, ids) -> str:
    res = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 200, res.text
    return res.json()["run_id"]


@pytest.mark.asyncio
async def test_save_collection_creates_collection_with_all_matched(client, api_app, workspace_id):
    ids = await _seed_two_molecules(api_app, workspace_id)
    run_id = await _ready_run_id(client, ids)

    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/save-collection",
        json={"name": "All matched"},
    )
    assert res.status_code == 201, res.text
    cid = res.json()["collection_id"]
    assert uuid.UUID(cid)

    members = await client.get(f"/api/v1/collections/{cid}/molecules")
    assert members.status_code == 200
    assert {uuid.UUID(m) for m in members.json()} == set(ids)


@pytest.mark.asyncio
async def test_save_collection_honors_rgroup_filter(client, api_app, workspace_id):
    ids = await _seed_two_molecules(api_app, workspace_id)
    run_id = await _ready_run_id(client, ids)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/save-collection",
        json={
            "name": "Filtered",
            "filter": {"registration_number": {"kind": "text", "op": "eq", "value": "CV-A"}},
        },
    )
    assert res.status_code == 201, res.text
    cid = res.json()["collection_id"]
    members = await client.get(f"/api/v1/collections/{cid}/molecules")
    assert {uuid.UUID(m) for m in members.json()} == {ids[0]}


@pytest.mark.asyncio
async def test_save_collection_rejects_empty_name(client, api_app, workspace_id):
    ids = await _seed_two_molecules(api_app, workspace_id)
    run_id = await _ready_run_id(client, ids)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/save-collection", json={"name": "   "}
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_save_collection_unknown_run_404(client):
    res = await client.post(
        f"/api/v1/sar/decomposition/{uuid.uuid4()}/save-collection", json={"name": "x"}
    )
    assert res.status_code == 404
