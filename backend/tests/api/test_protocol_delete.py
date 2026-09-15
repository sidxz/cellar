"""API: who may delete a draft protocol, the in-use refusal, and GET can_delete."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.api.conftest import _create_test_app
from tests.fakes.fake_auth import FakeAuth

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _client_as(
    database_url: str, workspace_id: uuid.UUID, **auth_kwargs
) -> AsyncIterator[AsyncClient]:
    auth = FakeAuth(workspace_id=workspace_id, **auth_kwargs)
    app = _create_test_app(database_url, auth)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac
    await app.state.container[AsyncEngine].dispose()


async def _make_draft(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": "Onboarding draft",
            "protocol_type": "biochemical",
            "readout_definitions": [{"name": "IC50", "data_type": "numeric", "display_order": 0}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def test_the_creating_editor_sees_can_delete_and_deletes(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID
) -> None:
    creator = uuid.uuid4()
    async with _client_as(database_url, workspace_id, role="editor", user_id=creator) as c:
        pid = await _make_draft(c)

        got = await c.get(f"/api/v1/protocols/{pid}")
        assert got.json()["can_delete"] is True

        assert (await c.delete(f"/api/v1/protocols/{pid}")).status_code == 204
        assert (await c.get(f"/api/v1/protocols/{pid}")).status_code == 404


async def test_another_editor_gets_403_and_can_delete_false(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID
) -> None:
    async with _client_as(database_url, workspace_id, role="editor", user_id=uuid.uuid4()) as c:
        pid = await _make_draft(c)
    other = uuid.uuid4()
    async with _client_as(database_url, workspace_id, role="editor", user_id=other) as c2:
        assert (await c2.get(f"/api/v1/protocols/{pid}")).json()["can_delete"] is False
        assert (await c2.delete(f"/api/v1/protocols/{pid}")).status_code == 403


async def test_a_draft_in_use_is_409_for_an_admin_and_names_the_usage(
    client: AsyncClient, api_app, workspace_id: uuid.UUID
) -> None:
    pid = await _make_draft(client)
    factory = api_app.state.container[async_sessionmaker]
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO compound_flags (id, workspace_id, molecule_id, protocol_id, "
                "flagged_by, flag_type, created_at) "
                "VALUES (:id, :ws, :mol, :proto, :user, 'star', now())"
            ),
            {
                "id": uuid.uuid4(),
                "ws": workspace_id,
                "mol": uuid.uuid4(),
                "proto": pid,
                "user": uuid.uuid4(),
            },
        )

    assert (await client.get(f"/api/v1/protocols/{pid}")).json()["can_delete"] is False
    resp = await client.delete(f"/api/v1/protocols/{pid}")
    assert resp.status_code == 409, resp.text
    assert "1 compound flag" in resp.text
