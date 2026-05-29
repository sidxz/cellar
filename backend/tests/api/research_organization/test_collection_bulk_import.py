"""API tests for bulk-add / preview-bulk + unregistered-rows handoff endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient


@pytest.fixture
async def client_with_collection(
    client: AsyncClient,
) -> AsyncIterator[tuple[AsyncClient, str, dict]]:
    """Spin a workspace + org + collection + one registered molecule.

    Returns ``(client, collection_id, {"reg_number": "CC-XXXXXX", "id": ...})``.
    """
    # Organization (molecule needs an originating_org_id)
    org = await client.post(
        "/api/v1/organizations",
        json={"name": "BulkImportTestOrg", "org_type": "internal"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    # Register a molecule we can resolve by reg_number
    mol = await client.post(
        "/api/v1/molecules",
        json={
            "name": "BulkImportTestMol",
            "smiles": "CCN",  # ethylamine — simple, deterministic
            "originating_org_id": org_id,
        },
    )
    assert mol.status_code == 201
    mol_payload = mol.json()
    existing_mol = {
        "id": mol_payload["molecule"]["id"],
        "reg_number": mol_payload["molecule"]["registration_number"],
    }

    # Collection
    coll = await client.post(
        "/api/v1/collections",
        json={"name": "BulkImportTestCollection"},
    )
    assert coll.status_code == 201
    collection_id = coll.json()["id"]

    yield client, collection_id, existing_mol


@pytest.mark.asyncio
async def test_preview_bulk_classifies_rows(
    client_with_collection: tuple[AsyncClient, str, dict],
) -> None:
    client, collection_id, existing_mol = client_with_collection
    body = {
        "rows": [
            {"row_index": 0, "registration_number": existing_mol["reg_number"]},
            {"row_index": 1, "smiles": "c1ccccc1O", "name": "phenol"},
            {"row_index": 2, "notes": "junk"},
        ],
    }
    response = await client.post(
        f"/api/v1/collections/{collection_id}/molecules/preview-bulk",
        json=body,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    statuses = {o["row_index"]: o["status"] for o in data["outcomes"]}
    assert statuses[0] in ("resolved", "already_present")
    assert statuses[1] == "unregistered"
    assert statuses[2] == "error"
    assert data["preview_id"] is not None


@pytest.mark.asyncio
async def test_bulk_commits_resolved_only(
    client_with_collection: tuple[AsyncClient, str, dict],
) -> None:
    client, collection_id, existing_mol = client_with_collection
    body = {
        "rows": [
            {"row_index": 0, "registration_number": existing_mol["reg_number"]},
            {"row_index": 1, "smiles": "c1ccccc1O"},
        ],
    }
    response = await client.post(
        f"/api/v1/collections/{collection_id}/molecules/bulk",
        json=body,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["resolved_count"] in (0, 1)
    assert data["unregistered_count"] == 1


@pytest.mark.asyncio
async def test_unregistered_rows_endpoint_returns_stash(
    client_with_collection: tuple[AsyncClient, str, dict],
) -> None:
    client, collection_id, _ = client_with_collection
    preview = await client.post(
        f"/api/v1/collections/{collection_id}/molecules/preview-bulk",
        json={"rows": [{"row_index": 0, "smiles": "c1ccccc1O", "name": "phenol"}]},
    )
    assert preview.status_code == 200, preview.text
    pid = preview.json()["preview_id"]
    assert pid is not None

    rows = await client.get(
        f"/api/v1/collection-import-previews/{pid}/unregistered-rows"
    )
    assert rows.status_code == 200, rows.text
    data = rows.json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["smiles"] == "c1ccccc1O"
    assert data["rows"][0]["name"] == "phenol"
    assert data["collection_id"] == str(collection_id)
