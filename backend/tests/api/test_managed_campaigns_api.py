"""A campaign managed by another app (DAIKON): only that app changes its structure.

The same structural call succeeds when the managing app makes it (a verified X-Service-Token,
here the acting-service dependency overridden) and is refused when ChemCellar's own client
makes it. Curation (notes, stage overrides, a cell pick) stays open to everyone.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.research_organization.campaign_management import CampaignManagement
from cellar.domain.shared.events import DomainEvent
from cellar.infrastructure.messaging.audit_event_handler import AuditEventHandler
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (  # noqa: E501
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.interface.dependencies._core import get_acting_service
from tests.api.test_campaign_stage_runs_api import (
    Seeded,
    _add_runs,
    _campaign,
    _config,
    _read,
    _seed,
    _stage,
)

DAIKON = CampaignManagement(
    managed_by="daikon",
    url="http://localhost:3002/screens/S1?round=R1&add_protocol=primary",
    label="Daikon",
)
MANAGED = "CampaignManagedElsewhereError"


@dataclass(frozen=True)
class Managed:
    seeded: Seeded
    campaign_id: str
    project_id: str
    stage_id: str
    channel_id: str
    result_id: str
    run_id: str


async def _manage(
    session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID, campaign_id: str
) -> None:
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        campaign = await repo.find_by_id_in_workspace(ws, uuid.UUID(campaign_id))
        assert campaign is not None
        campaign.set_management(DAIKON, user_id=None)
        await repo.save(campaign)
        await uow.commit()


async def _build(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    ws: uuid.UUID,
    *,
    managed: bool = True,
) -> Managed:
    """A campaign with one stage holding one run, its column and one compound row."""
    d = await _seed(session_factory, ws, [("10 µM", 40.0), ("10 µM", 60.0)])
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")
    await _add_runs(client, campaign_id, d, [d.run_ids[0]], stage_id)
    campaign = await _read(client, campaign_id)
    if managed:
        await _manage(session_factory, ws, campaign_id)
    return Managed(
        seeded=d,
        campaign_id=campaign_id,
        project_id=campaign["project_id"],
        stage_id=stage_id,
        channel_id=campaign["channels"][0]["id"],
        result_id=campaign["results"][0]["id"],
        run_id=d.run_ids[0],
    )


def _structural_calls(m: Managed) -> list[tuple[str, str, dict | None]]:
    """Every lifecycle or structural write: (method, path, json body)."""
    c = f"/api/v1/campaigns/{m.campaign_id}"
    other = str(uuid.uuid4())
    d = m.seeded
    return [
        ("PATCH", c, {"name": "Renamed"}),
        ("POST", f"{c}/close", {}),
        ("POST", f"{c}/reopen", {"reason": "more compounds"}),
        ("POST", f"{c}/supersede", {"new_campaign_id": other}),
        ("POST", f"{c}/refresh", None),
        ("POST", f"{c}/add-from-collection", {"collection_id": other}),
        ("POST", f"{c}/add-from-campaign", {"source_campaign_id": other}),
        (
            "POST",
            f"{c}/add-from-runs",
            {"run_ids": [d.run_ids[1]], "channel_configs": [_config(d)], "scope": "all"},
        ),
        ("POST", f"{c}/stages", {"name": "Confirmation"}),
        ("PATCH", f"{c}/stages/{m.stage_id}", {"name": "Primary screen"}),
        ("DELETE", f"{c}/stages/{m.stage_id}", None),
        ("DELETE", f"{c}/stages/{m.stage_id}/runs/{m.run_id}", None),
        (
            "POST",
            f"{c}/channels",
            {
                "label": "Signal again",
                "protocol_id": d.protocol_id,
                "readout_definition_id": d.readout_id,
                "source_kind": "readout_data",
                "selection_rule": "latest_run",
                "qualifier_handling": "include_qualified",
            },
        ),
        ("PATCH", f"{c}/channels/{m.channel_id}", {"label": "Signal %"}),
        ("DELETE", f"{c}/channels/{m.channel_id}", None),
        ("POST", f"{c}/channels/mirror-protocol", {"protocol_id": d.protocol_id}),
        ("POST", f"{c}/collections/{other}", None),
        ("DELETE", f"{c}/collections/{other}", None),
        ("POST", f"{c}/results", {"molecule_id": str(uuid.uuid4())}),
        ("DELETE", f"{c}/results/{m.result_id}", None),
        ("POST", f"{c}/results/bulk-remove", {"result_ids": [m.result_id]}),
    ]


STRUCTURAL = [
    "rename",
    "close",
    "reopen",
    "supersede",
    "refresh",
    "add-from-collection",
    "add-from-campaign",
    "add-from-runs",
    "add-stage",
    "edit-stage",
    "delete-stage",
    "remove-stage-run",
    "add-channel",
    "edit-channel",
    "delete-channel",
    "mirror-protocol",
    "link-collection",
    "unlink-collection",
    "add-row",
    "remove-row",
    "bulk-remove-rows",
]


@pytest.fixture
def acting_as(api_app: FastAPI) -> Iterator:
    """Make the next calls as a realm app (what a verified X-Service-Token yields)."""

    def _as(service: str | None) -> None:
        if service is None:
            api_app.dependency_overrides.pop(get_acting_service, None)
        else:
            api_app.dependency_overrides[get_acting_service] = lambda: service

    yield _as
    api_app.dependency_overrides.pop(get_acting_service, None)


async def _call(client: AsyncClient, method: str, path: str, body: dict | None):
    return await client.request(method, path, json=body)


@pytest.mark.parametrize("which", STRUCTURAL)
async def test_refused_from_chemcellar(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    which: str,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    method, path, body = dict(zip(STRUCTURAL, _structural_calls(m), strict=True))[which]
    response = await _call(client, method, path, body)
    assert response.status_code == 423, response.text
    error = response.json()
    assert error["error"] == MANAGED
    assert "managed in Daikon" in error["message"]
    assert (error["managed_by"], error["managed_label"], error["managed_url"]) == (
        "daikon",
        "Daikon",
        DAIKON.url,
    )


@pytest.mark.parametrize("which", STRUCTURAL)
async def test_managing_app_is_not_refused(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    acting_as,
    which: str,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    method, path, body = dict(zip(STRUCTURAL, _structural_calls(m), strict=True))[which]
    acting_as("daikon")
    response = await _call(client, method, path, body)
    # The call's own rules may still answer (a draft cannot be reopened, an unknown
    # collection is not found); only the managed refusal must not.
    assert response.status_code < 500, response.text
    assert response.status_code == 204 or response.json().get("error") != MANAGED, response.text


async def test_same_structural_call_succeeds_from_daikon_and_is_refused_from_chemcellar(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    acting_as,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    c = f"/api/v1/campaigns/{m.campaign_id}"

    refused = await client.post(f"{c}/stages", json={"name": "Confirmation"})
    assert refused.status_code == 423 and refused.json()["error"] == MANAGED
    refused = await client.patch(f"{c}/channels/{m.channel_id}", json={"label": "Signal %"})
    assert refused.status_code == 423 and refused.json()["error"] == MANAGED

    acting_as("daikon")
    added = await client.post(f"{c}/stages", json={"name": "Confirmation"})
    assert added.status_code == 200, added.text
    relabelled = await client.patch(f"{c}/channels/{m.channel_id}", json={"label": "Signal %"})
    assert relabelled.status_code == 200, relabelled.text

    acting_as(None)
    campaign = await _read(client, m.campaign_id)
    assert "Confirmation" in [s["name"] for s in campaign["stages"]]
    assert campaign["channels"][0]["label"] == "Signal %"


async def test_another_realm_app_is_refused(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    acting_as,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    acting_as("other-app")
    response = await client.post(
        f"/api/v1/campaigns/{m.campaign_id}/stages", json={"name": "Confirmation"}
    )
    assert response.status_code == 423 and response.json()["error"] == MANAGED


async def test_curation_stays_open_on_a_managed_campaign(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    c = f"/api/v1/campaigns/{m.campaign_id}"

    notes = await client.patch(f"{c}/results/{m.result_id}", json={"notes": "clean curve"})
    assert notes.status_code == 204, notes.text
    override = await client.put(
        f"{c}/stages/{m.stage_id}/overrides",
        json={"result_ids": [m.result_id], "outcome": "hit", "reason": "looked active"},
    )
    assert override.status_code == 204, override.text
    pick = await client.patch(
        f"{c}/results/{m.result_id}/cells/{m.channel_id}",
        json={"value": 50.0, "value_qualifier": "=", "unit": "%"},
    )
    assert pick.status_code < 300, pick.text


async def test_create_superseding_a_managed_campaign_is_refused(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    response = await client.post(
        "/api/v1/campaigns",
        json={
            "name": "Round 2",
            "project_id": m.project_id,
            "supersedes_campaign_id": m.campaign_id,
        },
    )
    assert response.status_code == 423 and response.json()["error"] == MANAGED


async def test_a_closed_managed_campaign_refuses_daikon_as_closed(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    acting_as,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    acting_as("daikon")
    closed = await client.post(f"/api/v1/campaigns/{m.campaign_id}/close", json={})
    assert closed.status_code == 200, closed.text
    response = await client.post(
        f"/api/v1/campaigns/{m.campaign_id}/stages", json={"name": "Confirmation"}
    )
    assert response.status_code == 423
    assert response.json()["error"] != MANAGED


async def test_an_unmanaged_campaign_is_unchanged(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    response = await client.post(
        f"/api/v1/campaigns/{m.campaign_id}/stages", json={"name": "Confirmation"}
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Create managed, mark an existing campaign, an admin releases it
# ---------------------------------------------------------------------------

_MARK = {"managed_url": DAIKON.url, "managed_label": "Daikon"}


async def _project(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/projects", json={"name": f"P-{uuid.uuid4().hex[:6]}"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_create_managed_from_daikon(client: AsyncClient, acting_as) -> None:
    project_id = await _project(client)
    acting_as("daikon")
    resp = await client.post(
        "/api/v1/campaigns", json={"name": "Round 1", "project_id": project_id, **_MARK}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["managed_by"], body["managed_url"], body["managed_label"]) == (
        "daikon",
        DAIKON.url,
        "Daikon",
    )


async def test_create_with_managed_fields_but_no_app_is_refused(client: AsyncClient) -> None:
    project_id = await _project(client)
    resp = await client.post(
        "/api/v1/campaigns", json={"name": "Round 1", "project_id": project_id, **_MARK}
    )
    assert resp.status_code == 422, resp.text


async def test_mark_an_existing_campaign_and_move_it(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    acting_as,
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    acting_as("daikon")
    marked = await client.put(f"/api/v1/campaigns/{m.campaign_id}/managed-by", json=_MARK)
    assert marked.status_code == 200, marked.text
    assert marked.json()["managed_by"] == "daikon"

    moved_url = "http://localhost:3002/screens/S2?round=R1"
    moved = await client.put(
        f"/api/v1/campaigns/{m.campaign_id}/managed-by",
        json={"managed_url": moved_url, "managed_label": "Daikon"},
    )
    assert moved.status_code == 200 and moved.json()["managed_url"] == moved_url


async def test_mark_without_an_app_is_forbidden(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], workspace_id
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    resp = await client.put(f"/api/v1/campaigns/{m.campaign_id}/managed-by", json=_MARK)
    assert resp.status_code == 403, resp.text


async def test_mark_a_campaign_another_app_manages_conflicts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    acting_as,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    acting_as("other-app")
    resp = await client.put(f"/api/v1/campaigns/{m.campaign_id}/managed-by", json=_MARK)
    assert resp.status_code == 409, resp.text


async def test_an_admin_releases_it_and_chemcellar_may_edit_again(
    client: AsyncClient,
    api_app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    # The shared test app leaves out the audit catch-all that production's lifespan wires.
    container = api_app.state.container
    container[EventDispatcher].register(
        DomainEvent, AuditEventHandler(container[async_sessionmaker])
    )
    released = await client.post(
        f"/api/v1/campaigns/{m.campaign_id}/release", json={"reason": "round abandoned"}
    )
    assert released.status_code == 200, released.text
    assert released.json()["managed_by"] is None

    stage = await client.post(
        f"/api/v1/campaigns/{m.campaign_id}/stages", json={"name": "Confirmation"}
    )
    assert stage.status_code == 200, stage.text

    async with session_factory() as s:
        reasons = (
            (
                await s.execute(
                    text("SELECT reason FROM audit_operations WHERE entity_id = :id"),
                    {"id": uuid.UUID(m.campaign_id)},
                )
            )
            .scalars()
            .all()
        )
    assert "round abandoned" in reasons


async def test_an_editor_may_not_release(
    client: AsyncClient,
    editor_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    resp = await editor_client.post(
        f"/api/v1/campaigns/{m.campaign_id}/release", json={"reason": "round abandoned"}
    )
    assert resp.status_code == 403, resp.text


async def test_the_campaign_list_shows_who_manages_it(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id)
    resp = await client.get("/api/v1/campaigns", params={"project_id": m.project_id})
    assert resp.status_code == 200, resp.text
    items = resp.json()
    items = items["items"] if isinstance(items, dict) else items
    [row] = [c for c in items if c["id"] == m.campaign_id]
    assert (row["managed_by"], row["managed_label"]) == ("daikon", "Daikon")
