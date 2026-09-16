"""API tests for GET /api/v1/plates/{plate_id}/runs (S15 §5.4 / §6).

The run plate is seeded directly (``PlateModel`` with ``registered_plate_id``
set) through the app's session factory — the plate-setup router isn't mounted
in the API test app and the ``:link`` route lives in a sibling task.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import PlateModel


async def _mk_plate(client: AsyncClient, **overrides) -> dict:
    body = {
        "barcode": f"PL-{uuid.uuid4().hex[:8]}",
        "plate_label": "Test Plate",
        "format": "96",
        "plate_type": "assay",
        **overrides,
    }
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_protocol(client: AsyncClient, name: str = "PlateRunsProto") -> str:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": name,
            "protocol_type": "biochemical",
            "readout_definitions": [{"name": "IC50", "data_type": "numeric", "display_order": 0}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    pid = resp.json()["id"]
    pub = await client.post(f"/api/v1/protocols/{pid}/publish")
    assert pub.status_code in (200, 201), pub.text
    return pid


async def _mk_run(client: AsyncClient, protocol_id: str, run_date: str = "2026-06-07") -> str:
    resp = await client.post(
        "/api/v1/runs", json={"protocol_id": protocol_id, "run_date": run_date}
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _link_run_plate(
    api_app: FastAPI, run_id: str, registered_plate_id: str, plate_number: int = 1
) -> None:
    factory = api_app.state.container[async_sessionmaker]
    async with factory() as session, session.begin():
        session.add(
            PlateModel(
                run_id=uuid.UUID(run_id),
                plate_number=plate_number,
                registered_plate_id=uuid.UUID(registered_plate_id),
            )
        )


class TestPlateRuns:
    async def test_linked_run_listed_once(self, client: AsyncClient, api_app: FastAPI) -> None:
        plate = await _mk_plate(client)
        pid = await _mk_protocol(client)
        rid = await _mk_run(client, pid)
        await _link_run_plate(api_app, rid, plate["id"], plate_number=2)

        resp = await client.get(f"/api/v1/plates/{plate['id']}/runs")

        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == rid
        assert row["plate_number"] == 2
        assert row["protocol_id"] == pid
        assert row["protocol_name"] == "PlateRunsProto"
        assert row["run_date"] == "2026-06-07"
        assert row["run_status"] == "draft"
        assert row["created_at"]

    async def test_newest_run_first(self, client: AsyncClient, api_app: FastAPI) -> None:
        plate = await _mk_plate(client)
        pid = await _mk_protocol(client)
        older = await _mk_run(client, pid, run_date="2026-06-01")
        newer = await _mk_run(client, pid, run_date="2026-06-02")
        await _link_run_plate(api_app, older, plate["id"])
        await _link_run_plate(api_app, newer, plate["id"])

        resp = await client.get(f"/api/v1/plates/{plate['id']}/runs")

        assert resp.status_code == 200, resp.text
        assert [r["run_id"] for r in resp.json()] == [newer, older]

    async def test_unlinked_plate_is_empty(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)

        resp = await client.get(f"/api/v1/plates/{plate['id']}/runs")

        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    async def test_missing_plate_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/plates/{uuid.uuid4()}/runs")
        assert resp.status_code == 404

    async def test_hidden_foreign_org_plate_404(
        self,
        client: AsyncClient,
        api_app: FastAPI,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        theirs = await _mk_plate(editor_client_other_org)  # owner = OTHER_ORG
        pid = await _mk_protocol(client)
        rid = await _mk_run(client, pid)
        await _link_run_plate(api_app, rid, theirs["id"])

        # hidden == missing: a linked run must not leak the plate's existence
        resp = await editor_client_own_org.get(f"/api/v1/plates/{theirs['id']}/runs")
        assert resp.status_code == 404, resp.text

        # the owner org still sees it
        resp = await editor_client_other_org.get(f"/api/v1/plates/{theirs['id']}/runs")
        assert resp.status_code == 200, resp.text
        assert [r["run_id"] for r in resp.json()] == [rid]

    async def test_viewer_allowed(
        self,
        client: AsyncClient,
        api_app: FastAPI,
        editor_client: AsyncClient,
        viewer_client: AsyncClient,
    ) -> None:
        # editor_client has no org -> owner_org_id is NULL -> visible to the
        # org-less viewer under the strict rule (only org-owned plates are excluded).
        plate = await _mk_plate(editor_client)
        assert plate["owner_org_id"] is None
        pid = await _mk_protocol(client)
        rid = await _mk_run(client, pid)
        await _link_run_plate(api_app, rid, plate["id"])

        resp = await viewer_client.get(f"/api/v1/plates/{plate['id']}/runs")

        assert resp.status_code == 200, resp.text
        assert [r["run_id"] for r in resp.json()] == [rid]
