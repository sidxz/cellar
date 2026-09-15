"""End-to-end API tests for admin hard-delete (Tier 1 — vocabulary) and
Tier-2 cascade preview + cascade delete.

HTTPX note: AsyncClient.delete() does not support a `json` body parameter.
Use client.request("DELETE", url, json=...) for DELETE requests with a body.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Force cascade rules and models into process-global registry for API tests.
import cellar.infrastructure.cascade.rules_screening_assay
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_vocab(client: AsyncClient, name: str) -> dict:
    """Create a vocabulary via the public API and return the response body."""
    resp = await client.post("/api/v1/vocabularies", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _admin_delete(client: AsyncClient, entity_type: str, entity_id: str, reason: str):
    """Issue an admin DELETE with a JSON body (workaround for httpx delete limit)."""
    return await client.request(
        "DELETE",
        f"/api/v1/admin/{entity_type}/{entity_id}",
        json={"reason": reason},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdminHardDelete:
    async def test_admin_can_delete_unreferenced_vocabulary(self, client: AsyncClient) -> None:
        """Admin deletes an unreferenced vocabulary → 204."""
        vocab = await _create_vocab(client, "Solvents-T1")
        resp = await _admin_delete(client, "vocabulary", vocab["id"], "obsolete")
        assert resp.status_code == 204

    async def test_editor_cannot_admin_delete(
        self, client: AsyncClient, editor_client: AsyncClient
    ) -> None:
        """Editor calling admin endpoint → 403."""
        vocab = await _create_vocab(client, "Solvents-T2")
        resp = await _admin_delete(editor_client, "vocabulary", vocab["id"], "x")
        assert resp.status_code == 403

    async def test_missing_reason_422(self, client: AsyncClient) -> None:
        """Admin calls with empty reason body → 422."""
        vocab = await _create_vocab(client, "Solvents-T3")
        resp = await _admin_delete(client, "vocabulary", vocab["id"], "")
        assert resp.status_code == 422

    async def test_unknown_entity_type_404(self, client: AsyncClient) -> None:
        """Admin calls /admin/wat/<uuid> → 404 (entity_type not in registry)."""
        resp = await _admin_delete(client, "wat", str(uuid.uuid4()), "x")
        assert resp.status_code == 404

    async def test_audit_operation_recorded(self, client: AsyncClient) -> None:
        """After a successful delete, an admin_hard_delete audit operation exists."""
        vocab = await _create_vocab(client, "Solvents-T5")
        vid = vocab["id"]

        delete_resp = await _admin_delete(client, "vocabulary", vid, "obsolete")
        assert delete_resp.status_code == 204

        # Query audit log for this entity via the audit API
        audit_resp = await client.get(
            "/api/v1/audit",
            params={"entity_type": "vocabulary", "entity_id": vid},
        )
        assert audit_resp.status_code == 200
        ops = audit_resp.json()["items"]

        hard_deletes = [op for op in ops if op["operation_type"] == "admin_hard_delete"]
        assert hard_deletes, "Expected at least one admin_hard_delete audit operation"

        op = hard_deletes[0]
        assert op["reason"] == "obsolete"
        assert any(e["entry_type"] == "delete" for e in op["entries"])

    async def test_a_rule_reference_blocks_tier1_hard_delete(
        self, client: AsyncClient, api_app: FastAPI, workspace_id: uuid.UUID
    ) -> None:
        """A compound flag has no FK to its protocol, but still refuses a Tier-1 delete."""
        protocol_id = uuid.uuid4()
        await _raw_insert_protocol(
            api_app, protocol_id, f"T1-Flagged-{protocol_id.hex[:6]}", workspace_id
        )
        async with await _get_session(api_app) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO compound_flags (id, workspace_id, molecule_id, protocol_id, "
                    "flagged_by, flag_type, created_at) "
                    "VALUES (:id, :ws, :mol, :proto, :user, 'pains', now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "mol": uuid.uuid4(),
                    "proto": protocol_id,
                    "user": uuid.uuid4(),
                },
            )
            await session.commit()

        resp = await _admin_delete(client, "protocol", str(protocol_id), "duplicate registration")

        assert resp.status_code == 409, resp.text
        [blocker] = resp.json()["blockers"]
        assert (blocker["table"], blocker["display_label"], blocker["count"]) == (
            "compound_flags",
            "Compound flags",
            1,
        )


# ---------------------------------------------------------------------------
# Tier-2 helpers — raw SQL inserts (API protocol creation requires too much
# workspace setup; direct inserts match the cascade integration test pattern).
# ---------------------------------------------------------------------------

_USER_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000014")


async def _get_session(api_app: FastAPI) -> AsyncSession:
    """Return a session connected to the test DB via the app container's engine."""
    engine: AsyncEngine = api_app.state.container[AsyncEngine]
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory()


async def _raw_insert_protocol(
    api_app: FastAPI,
    protocol_id: uuid.UUID,
    name: str,
    workspace_id: uuid.UUID,
) -> None:
    """Insert a protocol in the given workspace (must match the admin auth workspace)."""
    async with await _get_session(api_app) as session:
        await session.execute(
            sa.text(
                "INSERT INTO organizations "
                "(id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'T14 Org', 'internal', true, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": _USER_ID, "ws": workspace_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO protocols "
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
                "VALUES (:id, :ws, :name, 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "id": protocol_id,
                "ws": workspace_id,
                "name": name,
                "user": _USER_ID,
            },
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Tier-2 tests
# ---------------------------------------------------------------------------


class TestCascadeTier2:
    async def test_cascade_preview_protocol(
        self, client: AsyncClient, api_app: FastAPI, workspace_id: uuid.UUID
    ) -> None:
        """Admin previews cascade tree for a protocol — returns 200 with CascadeNode JSON."""
        protocol_id = uuid.uuid4()
        proto_name = f"T14-Preview-{protocol_id.hex[:6]}"
        await _raw_insert_protocol(api_app, protocol_id, proto_name, workspace_id)

        resp = await client.post(f"/api/v1/admin/protocol/{protocol_id}/cascade-preview")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity_type"] == "protocol"
        assert body["table"] == "protocols"
        assert "children" in body
        assert body["blockers"] == []
        assert body["warnings"] == []

    async def test_cascade_delete_requires_typed_name(
        self, client: AsyncClient, api_app: FastAPI, workspace_id: uuid.UUID
    ) -> None:
        """Cascade delete with wrong typed_name → 422."""
        protocol_id = uuid.uuid4()
        proto_name = f"T14-WrongName-{protocol_id.hex[:6]}"
        await _raw_insert_protocol(api_app, protocol_id, proto_name, workspace_id)

        resp = await client.request(
            "DELETE",
            f"/api/v1/admin/protocol/{protocol_id}/cascade",
            json={"typed_name": "definitely-wrong-name", "reason": "test cleanup"},
        )
        assert resp.status_code == 422, resp.text

    async def test_cascade_delete_succeeds(
        self, client: AsyncClient, api_app: FastAPI, workspace_id: uuid.UUID
    ) -> None:
        """Cascade delete with correct typed_name + reason → 204."""
        protocol_id = uuid.uuid4()
        proto_name = f"T14-Delete-{protocol_id.hex[:6]}"
        await _raw_insert_protocol(api_app, protocol_id, proto_name, workspace_id)

        resp = await client.request(
            "DELETE",
            f"/api/v1/admin/protocol/{protocol_id}/cascade",
            json={"typed_name": proto_name, "reason": "test cleanup"},
        )
        assert resp.status_code == 204, resp.text

    async def test_tier2_only_for_pilot_entities(self, client: AsyncClient) -> None:
        """Vocabulary is NOT in TIER2_ENTITY_TYPES; cascade-preview on it returns 404."""
        resp = await client.post(f"/api/v1/admin/vocabulary/{uuid.uuid4()}/cascade-preview")
        assert resp.status_code == 404, resp.text

    async def test_cascade_delete_blocked_returns_every_blocker(
        self, client: AsyncClient, api_app: FastAPI, workspace_id: uuid.UUID
    ) -> None:
        """A block rule refuses the cascade with the Tier-1 409 body."""
        protocol_id = uuid.uuid4()
        proto_name = f"T14-Blocked-{protocol_id.hex[:6]}"
        await _raw_insert_protocol(api_app, protocol_id, proto_name, workspace_id)
        async with await _get_session(api_app) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO import_templates (id, workspace_id, name, column_mappings, "
                    "created_by, default_protocol_id) "
                    "VALUES (:id, :ws, 'CRO sheet', CAST('{}' AS jsonb), :user, :proto)"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "user": uuid.uuid4(),
                    "proto": protocol_id,
                },
            )
            await session.commit()

        resp = await client.request(
            "DELETE",
            f"/api/v1/admin/protocol/{protocol_id}/cascade",
            json={"typed_name": proto_name, "reason": "duplicate registration"},
        )

        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error"] == "delete_blocked_by_dependencies"
        assert [b["display_label"] for b in body["blockers"]] == [
            "Plate import templates defaulting to this protocol"
        ]
