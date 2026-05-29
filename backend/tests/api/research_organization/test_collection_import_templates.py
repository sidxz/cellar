"""API tests for CollectionImportTemplate CRUD endpoints."""

from __future__ import annotations

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
