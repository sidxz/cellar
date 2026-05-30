"""API tests for RegisteredPlate well-role harmonization.

Control wells (no batch) exercise the role + concentration flow end-to-end
without needing to seed a batch through the resolver.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _register(client: AsyncClient, **overrides):
    body = {
        "barcode": f"PLT-{uuid.uuid4().hex[:8]}",
        "plate_label": "Test Plate",
        "format": "96",
        "plate_type": "assay",
    }
    body.update(overrides)
    return await client.post("/api/v1/plates", json=body)


class TestWellRoles:
    async def test_register_with_control_well_returns_flat_shape(
        self, client: AsyncClient
    ) -> None:
        resp = await _register(
            client,
            well_map={
                "A1": {
                    "well_type": "positive_control",
                    "concentration_value": 5.0,
                    "concentration_unit": "uM",
                }
            },
        )
        assert resp.status_code == 201, resp.text
        wm = resp.json()["well_map"]
        assert wm["A1"] == {
            "batch_id": None,
            "concentration_value": 5.0,
            "concentration_unit": "uM",
            "well_type": "positive_control",
            "cdd_batch_id_unresolved": None,
        }

    async def test_map_wells_endpoint_sets_role(self, client: AsyncClient) -> None:
        reg = await _register(client)
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        resp = await client.put(
            f"/api/v1/plates/{plate_id}/wells",
            json={"well_map": {"B2": {"well_type": "negative_control"}}},
        )
        assert resp.status_code == 200, resp.text
        well = resp.json()["well_map"]["B2"]
        assert well["well_type"] == "negative_control"
        assert well["batch_id"] is None

    async def test_invalid_well_type_rejected(self, client: AsyncClient) -> None:
        resp = await _register(client, well_map={"A1": {"well_type": "bogus"}})
        assert resp.status_code >= 400
