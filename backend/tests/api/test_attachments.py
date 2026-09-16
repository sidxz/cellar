"""API tests: attachment upload/download land under STORAGE_ROOT.

Regression for the prod bug where the storage client read a different env var
than the one the deploy sets, so files never reached the mounted volume.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import AsyncClient


@pytest.fixture
async def molecule_id(client: AsyncClient) -> str:
    org = await client.post(
        "/api/v1/organizations", json={"name": "AttachTestOrg", "org_type": "internal"}
    )
    assert org.status_code == 201, org.text
    mol = await client.post(
        "/api/v1/molecules",
        json={"name": "Attach-X", "smiles": "CCO", "originating_org_id": org.json()["id"]},
    )
    assert mol.status_code == 201, mol.text
    return mol.json()["molecule"]["id"]


@pytest.mark.asyncio
async def test_upload_lands_under_storage_root_and_downloads_back(
    client: AsyncClient, molecule_id: str
) -> None:
    payload = b"smiles,name\nCCO,ethanol\n"
    up = await client.post(
        f"/api/v1/molecule/{molecule_id}/attachments",
        files={"file": ("notes.csv", payload, "text/csv")},
    )
    assert up.status_code == 201, up.text
    attachment_id = up.json()["id"]

    down = await client.get(f"/api/v1/attachments/{attachment_id}/download")
    assert down.status_code == 200, down.text
    assert down.content == payload

    root = Path(os.environ["STORAGE_ROOT"])
    on_disk = list((root / "attachments").rglob("*notes.csv"))
    assert len(on_disk) == 1, f"expected the file under {root}/attachments, got {on_disk}"
    assert on_disk[0].read_bytes() == payload
