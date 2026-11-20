"""API tests for CollectionImportTemplate CRUD endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_template(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/collection-import-templates",
        json={
            "name": "Partner ACME Q3",
            "column_mapping": {
                "registration_number": "Reg No.",
                "name": "Compound",
            },
        },
    )
    assert create.status_code == 201, create.text
    tid = create.json()["id"]

    listing = await client.get("/api/v1/collection-import-templates")
    assert listing.status_code == 200, listing.text
    assert any(t["id"] == tid for t in listing.json())


@pytest.mark.asyncio
async def test_update_and_delete_template(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/collection-import-templates",
        json={"name": "t1", "column_mapping": {"name": "X"}},
    )
    assert create.status_code == 201, create.text
    tid = create.json()["id"]

    upd = await client.put(
        f"/api/v1/collection-import-templates/{tid}",
        json={"column_mapping": {"name": "X", "smiles": "Structure"}},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["column_mapping"]["smiles"] == "Structure"

    delete = await client.delete(f"/api/v1/collection-import-templates/{tid}")
    assert delete.status_code == 204, delete.text


@pytest.mark.asyncio
async def test_list_without_collection_id_returns_false_used_here(
    client: AsyncClient,
) -> None:
    create = await client.post(
        "/api/v1/collection-import-templates",
        json={"name": "t-no-collection", "column_mapping": {"name": "X"}},
    )
    assert create.status_code == 201, create.text
    tid = create.json()["id"]

    listing = await client.get("/api/v1/collection-import-templates")
    assert listing.status_code == 200, listing.text
    found = next(t for t in listing.json() if t["id"] == tid)
    assert found["used_in_this_collection"] is False


@pytest.mark.asyncio
async def test_list_with_collection_id_marks_used_here_when_in_usage_list(
    client: AsyncClient,
) -> None:
    """A commit that resolves a row with a template records the collection on
    the template; listing for that collection then marks it used here."""
    create = await client.post(
        "/api/v1/collection-import-templates",
        json={"name": "t-with-collection", "column_mapping": {"name": "X"}},
    )
    assert create.status_code == 201, create.text
    tid = create.json()["id"]

    org = await client.post(
        "/api/v1/organizations", json={"name": "TemplateUsageOrg", "org_type": "internal"}
    )
    mol = await client.post(
        "/api/v1/molecules",
        json={"name": "TemplateUsageMol", "smiles": "CCN", "originating_org_id": org.json()["id"]},
    )
    assert mol.status_code == 201, mol.text
    reg_number = mol.json()["molecule"]["registration_number"]
    coll = await client.post("/api/v1/collections", json={"name": "TemplateUsageCollection"})
    collection_id = coll.json()["id"]

    bulk = await client.post(
        f"/api/v1/collections/{collection_id}/molecules/bulk",
        json={"rows": [{"row_index": 0, "registration_number": reg_number}], "template_id": tid},
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["resolved_count"] == 1

    def used_in(listing: list[dict]) -> bool:
        return next(t for t in listing if t["id"] == tid)["used_in_this_collection"]

    url = "/api/v1/collection-import-templates"
    here = await client.get(url, params={"collection_id": collection_id})
    elsewhere = await client.get(url, params={"collection_id": str(uuid.uuid4())})
    assert used_in(here.json()) is True
    assert used_in(elsewhere.json()) is False
