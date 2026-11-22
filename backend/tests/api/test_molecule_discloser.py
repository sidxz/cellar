"""PUT /api/v1/molecules/{id}/discloser: an admin or the registrant corrects who disclosed it."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.infrastructure.messaging.audit_event_handler import register_audit_handler
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher

from tests.api.conftest import OTHER_ORG_ID


@pytest.fixture
async def molecule(client: AsyncClient) -> dict:
    org = await client.post(
        "/api/v1/organizations", json={"name": "DiscloserOrg", "org_type": "internal"}
    )
    resp = await client.post(
        "/api/v1/molecules",
        json={"name": "Disclosed-1", "smiles": "CCCOC", "originating_org_id": org.json()["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["molecule"]


async def test_put_discloser_changes_and_history_records_it(
    api_app, client: AsyncClient, molecule: dict
) -> None:
    container = api_app.state.container  # as the app's lifespan does
    register_audit_handler(container[EventDispatcher], container[async_sessionmaker])
    resp = await client.put(
        f"/api/v1/molecules/{molecule['id']}/discloser",
        json={"disclosed_by": molecule["registered_by"], "disclosed_by_org_id": str(OTHER_ORG_ID)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["disclosed_by_org_id"] == str(OTHER_ORG_ID)

    audit = await client.get(
        "/api/v1/audit", params={"entity_type": "Molecule", "entity_id": molecule["id"]}
    )
    entries = [e for op in audit.json()["items"] for e in op["entries"]]
    change = next(e for e in entries if e["field_name"] == "disclosed_by_org_id")
    assert (change["old_value"], change["new_value"]) == (
        molecule["disclosed_by_org_id"],
        str(OTHER_ORG_ID),
    )


async def test_put_discloser_non_registrant_editor_403(
    molecule: dict, other_editor_client: AsyncClient
) -> None:
    resp = await other_editor_client.put(
        f"/api/v1/molecules/{molecule['id']}/discloser",
        json={"disclosed_by": molecule["registered_by"], "disclosed_by_org_id": str(OTHER_ORG_ID)},
    )
    assert resp.status_code == 403
