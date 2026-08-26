"""API tests: run plate ↔ inventory plate link (S15 spec §6).

``POST /runs/{run_id}/plates/{plate_id}:link`` / ``:unlink`` and the
``registered_plate_*`` fields on ``GET /runs/{run_id}/plate-map``.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _mk_plate(client: AsyncClient, barcode: str, **overrides) -> dict:
    body = {
        "barcode": barcode,
        "plate_label": barcode,
        "format": "96",
        "plate_type": "assay",
        **overrides,
    }
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_run(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": f"LinkProto-{uuid.uuid4().hex[:6]}",
            "protocol_type": "biochemical",
            "readout_definitions": [{"name": "IC50", "data_type": "numeric", "display_order": 0}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    pid = resp.json()["id"]
    assert (await client.post(f"/api/v1/protocols/{pid}/publish")).status_code in (200, 201)
    resp = await client.post("/api/v1/runs", json={"protocol_id": pid, "run_date": "2026-08-26"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _mk_run_plate(client: AsyncClient, run_id: str) -> str:
    resp = await client.post(
        f"/api/v1/runs/{run_id}/plate-setup",
        json={"plate_number": 1, "compound_assignments": []},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["plate_id"]


async def _link(client: AsyncClient, run_id: str, plate_id: str, barcode: str):
    return await client.post(
        f"/api/v1/runs/{run_id}/plates/{plate_id}:link", json={"barcode": barcode}
    )


async def _plate_map_entry(client: AsyncClient, run_id: str, plate_id: str) -> dict:
    resp = await client.get(f"/api/v1/runs/{run_id}/plate-map")
    assert resp.status_code == 200, resp.text
    return next(p for p in resp.json()["plates"] if p["plate_id"] == plate_id)


class TestLink:
    async def test_link_by_exact_barcode(self, client: AsyncClient) -> None:
        inv = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", plate_label="Mother 1")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        resp = await _link(client, run_id, plate_id, inv["barcode"])

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "plate_id": plate_id,
            "registered_plate_id": inv["id"],
            "barcode": inv["barcode"],
            "plate_label": "Mother 1",
        }

    async def test_link_by_zero_padded_barcode(self, client: AsyncClient) -> None:
        inv = await _mk_plate(client, "000123")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        resp = await _link(client, run_id, plate_id, "123")

        assert resp.status_code == 200, resp.text
        assert resp.json()["registered_plate_id"] == inv["id"]

    async def test_link_by_label(self, client: AsyncClient) -> None:
        inv = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", plate_label="SAC3-014-3070")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        resp = await _link(client, run_id, plate_id, "SAC3-014-3070")

        assert resp.status_code == 200, resp.text
        assert resp.json()["registered_plate_id"] == inv["id"]

    async def test_unknown_reference_is_404(self, client: AsyncClient) -> None:
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        resp = await _link(client, run_id, plate_id, "does-not-exist")

        assert resp.status_code == 404, resp.text

    async def test_plate_not_on_run_is_404(self, client: AsyncClient) -> None:
        inv = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        run_id = await _mk_run(client)

        resp = await _link(client, run_id, str(uuid.uuid4()), inv["barcode"])

        assert resp.status_code == 404, resp.text

    async def test_hidden_other_org_plate_is_404(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        # Owned by AUTH_ORG_ID (the admin client's org); the other-org editor can't see it.
        inv = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        resp = await _link(editor_client_other_org, run_id, plate_id, inv["barcode"])

        assert resp.status_code == 404, resp.text

    async def test_relink_overwrites(self, client: AsyncClient) -> None:
        first = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        second = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)
        assert (await _link(client, run_id, plate_id, first["barcode"])).status_code == 200

        resp = await _link(client, run_id, plate_id, second["barcode"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["registered_plate_id"] == second["id"]
        entry = await _plate_map_entry(client, run_id, plate_id)
        assert entry["registered_plate_id"] == second["id"]

    async def test_viewer_is_403(self, client: AsyncClient, viewer_client: AsyncClient) -> None:
        inv = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        resp = await _link(viewer_client, run_id, plate_id, inv["barcode"])

        assert resp.status_code == 403, resp.text

    async def test_locked_run_is_409(self, client: AsyncClient) -> None:
        inv = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)
        assert (await client.post(f"/api/v1/runs/{run_id}/start")).status_code == 200
        assert (
            await client.post(
                f"/api/v1/runs/{run_id}/complete", json={"plate_count": 1, "data_point_count": 0}
            )
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/runs/{run_id}/lock", json={"reason": "qc"})
        ).status_code == 200

        resp = await _link(client, run_id, plate_id, inv["barcode"])

        assert resp.status_code == 409, resp.text


class TestUnlinkAndPlateMap:
    async def test_plate_map_carries_link_and_unlink_clears_it(self, client: AsyncClient) -> None:
        inv = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", plate_label="Mother 2")
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        entry = await _plate_map_entry(client, run_id, plate_id)
        assert entry["registered_plate_id"] is None
        assert entry["registered_plate_barcode"] is None
        assert entry["registered_plate_label"] is None

        assert (await _link(client, run_id, plate_id, inv["barcode"])).status_code == 200
        entry = await _plate_map_entry(client, run_id, plate_id)
        assert entry["registered_plate_id"] == inv["id"]
        assert entry["registered_plate_barcode"] == inv["barcode"]
        assert entry["registered_plate_label"] == "Mother 2"

        resp = await client.post(f"/api/v1/runs/{run_id}/plates/{plate_id}:unlink")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "plate_id": plate_id,
            "registered_plate_id": None,
            "barcode": None,
            "plate_label": None,
        }
        entry = await _plate_map_entry(client, run_id, plate_id)
        assert entry["registered_plate_id"] is None

    async def test_unlink_viewer_is_403(
        self, client: AsyncClient, viewer_client: AsyncClient
    ) -> None:
        run_id = await _mk_run(client)
        plate_id = await _mk_run_plate(client, run_id)

        resp = await viewer_client.post(f"/api/v1/runs/{run_id}/plates/{plate_id}:unlink")

        assert resp.status_code == 403, resp.text
